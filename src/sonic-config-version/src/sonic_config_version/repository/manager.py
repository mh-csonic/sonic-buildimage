import json
import os
import pwd

from sonic_config_version.constants import (
    ACTIVE_REF,
    CONFIG_PATH,
    METADATA_PATH,
    MIN_FREE_BYTES,
    MIN_FREE_INODES,
)
from sonic_config_version.errors import NoChangeError, RepositoryError, ValidationError
from sonic_config_version.repository.git_runner import GitRunner, validate_revision
from sonic_config_version.snapshot.metadata import create_metadata, validate_metadata
from sonic_config_version.snapshot.normalizer import digest, normalize
from sonic_config_version.storage import Storage, has_strict_permissions


ZERO_SHA = "0" * 40


class Repository:
    def __init__(self, storage, git_path=None, required_uid=0):
        self.storage = storage
        kwargs = {} if git_path is None else {"git_path": git_path}
        self.git = GitRunner(storage.repository, storage.base_dir, **kwargs)
        self.required_uid = required_uid

    def initialize_repository(self):
        if self.git.exists():
            return
        self.storage.ensure_layout()
        self.git.run("init", "--quiet", "--initial-branch=main", "--template=")
        self.git.run("config", "--local", "user.name", "SonicGit")
        self.git.run("config", "--local", "user.email", "sonicgit@localhost")
        self.git.run("config", "--local", "core.hooksPath", "/dev/null")
        self.git.run("config", "--local", "gc.auto", "0")
        self._tighten_modes()

    def _tighten_modes(self):
        for root, directories, files in os.walk(self.storage.repository, followlinks=False):
            os.chmod(root, 0o700)
            for directory in directories:
                path = os.path.join(root, directory)
                if os.path.islink(path):
                    raise RepositoryError("symlink found in repository: {}".format(path))
                os.chmod(path, 0o700)
            for filename in files:
                path = os.path.join(root, filename)
                if os.path.islink(path):
                    raise RepositoryError("symlink found in repository: {}".format(path))
                os.chmod(path, 0o600)

    def _verify_tree_security(self):
        for root, directories, files in os.walk(self.storage.repository, followlinks=False):
            has_strict_permissions(root, self.required_uid)
            for name in directories + files:
                has_strict_permissions(os.path.join(root, name), self.required_uid)

    def preflight(self, allow_uninitialized=False):
        self.storage.ensure_layout()
        self.storage.check_capacity(MIN_FREE_BYTES, MIN_FREE_INODES)
        has_strict_permissions(self.storage.base_dir, self.required_uid)
        has_strict_permissions(self.storage.repository, self.required_uid)
        if not self.git.exists():
            if allow_uninitialized:
                return
            raise RepositoryError("SonicGit repository is not initialized")
        self._verify_tree_security()
        self.git.run("fsck", "--no-dangling")
        if self.remote_count():
            raise RepositoryError("configured Git remotes are not permitted")
        status, _ = self.git.run("status", "--porcelain")
        if status.strip():
            raise RepositoryError("repository work tree has unexpected changes")

    def remote_count(self):
        if not self.git.exists():
            return 0
        output, _ = self.git.run("remote")
        return len([line for line in output.splitlines() if line.strip()])

    def resolve_optional_ref(self, reference):
        if not self.git.exists():
            return None
        output, _ = self.git.run("rev-parse", "--verify", "--quiet", reference, check=False)
        candidate = output.strip()
        return candidate if len(candidate) == 40 else None

    def resolve_revision(self, revision):
        validate_revision(revision)
        output, _ = self.git.run("rev-parse", "--verify", "{}^{{commit}}".format(revision))
        sha = output.strip()
        if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha.lower()):
            raise RepositoryError("revision did not resolve to a full commit SHA")
        return sha

    def update_ref(self, reference, new_sha):
        old_sha = self.resolve_optional_ref(reference)
        self.git.run("update-ref", reference, new_sha, old_sha or ZERO_SHA)
        self._tighten_modes()

    def restore_ref(self, reference, sha):
        current = self.resolve_optional_ref(reference)
        if sha:
            self.git.run("update-ref", reference, sha, current or ZERO_SHA)
        elif current:
            self.git.run("update-ref", "-d", reference, current)
        self._tighten_modes()

    def commit_snapshot(self, normalized, snapshot_hash, message, operator, system_info, allow_empty=False):
        current = self.resolve_optional_ref(ACTIVE_REF)
        old_head = self.resolve_optional_ref("HEAD")
        if current:
            current_snapshot, _ = self.load_snapshot(current)
            if digest(current_snapshot) == snapshot_hash and not allow_empty:
                raise NoChangeError("running configuration is identical to the active commit")
        commit_message = " ".join(message.split())[:512] or "SonicGit snapshot"
        metadata = create_metadata(snapshot_hash, operator, commit_message, system_info, current)
        config_file = os.path.join(self.storage.repository, CONFIG_PATH)
        metadata_file = os.path.join(self.storage.repository, METADATA_PATH)
        Storage.atomic_write(config_file, normalized)
        Storage.atomic_write_json(metadata_file, metadata)
        self.git.run("add", "--", CONFIG_PATH, METADATA_PATH)
        tree, _ = self.git.run("write-tree")
        arguments = ["commit-tree", tree.strip(), "-m", commit_message]
        if current:
            arguments.extend(["-p", current])
        commit_output, _ = self.git.run(*arguments)
        sha = commit_output.strip()
        if len(sha) != 40:
            raise RepositoryError("Git did not return a full commit SHA")
        archive_ref = "refs/sonic/commits/{}".format(sha)
        archive_old = self.resolve_optional_ref(archive_ref)
        commands = ["start"]
        commands.append("update HEAD {} {}".format(sha, old_head) if old_head else "create HEAD {}".format(sha))
        commands.append(
            "update {} {} {}".format(archive_ref, sha, archive_old)
            if archive_old
            else "create {} {}".format(archive_ref, sha)
        )
        commands.append(
            "update {} {} {}".format(ACTIVE_REF, sha, current)
            if current
            else "create {} {}".format(ACTIVE_REF, sha)
        )
        commands.append("commit")
        try:
            self.git.run("update-ref", "--stdin", input_text="\n".join(commands) + "\n")
        except Exception:
            self._restore_worktree(old_head)
            raise
        self._tighten_modes()
        return sha, metadata

    def _restore_worktree(self, old_head):
        config_file = os.path.join(self.storage.repository, CONFIG_PATH)
        metadata_file = os.path.join(self.storage.repository, METADATA_PATH)
        if old_head:
            old_config, _ = self.git.run("show", "{}:{}".format(old_head, CONFIG_PATH))
            old_metadata, _ = self.git.run("show", "{}:{}".format(old_head, METADATA_PATH))
            Storage.atomic_write(config_file, old_config.encode("utf-8"))
            Storage.atomic_write(metadata_file, old_metadata.encode("utf-8"))
            self.git.run("read-tree", old_head)
        else:
            for path in (config_file, metadata_file):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
            self.git.run("read-tree", "--empty")
        self._tighten_modes()

    def load_snapshot(self, revision):
        sha = self.resolve_revision(revision)
        names, _ = self.git.run("ls-tree", "-r", "--name-only", sha)
        actual = set(names.splitlines())
        required = {CONFIG_PATH, METADATA_PATH}
        if actual != required:
            raise ValidationError("commit tree must contain only {}".format(", ".join(sorted(required))))
        config_text, _ = self.git.run("show", "{}:{}".format(sha, CONFIG_PATH))
        metadata_text, _ = self.git.run("show", "{}:{}".format(sha, METADATA_PATH))
        normalized = normalize(config_text)
        if config_text.encode("utf-8") != normalized:
            raise ValidationError("commit configuration is not normalization-version canonical JSON")
        try:
            metadata = json.loads(metadata_text)
        except ValueError as exc:
            raise ValidationError("invalid commit metadata JSON: {}".format(exc))
        validate_metadata(metadata, digest(normalized))
        parent_output, _ = self.git.run("rev-list", "--parents", "-n", "1", sha)
        parent_fields = parent_output.split()
        actual_parent = parent_fields[1] if len(parent_fields) > 1 else None
        if metadata["parent"] != actual_parent:
            raise ValidationError("commit metadata parent does not match the Git parent")
        return normalized, metadata

    def history(self, limit=20):
        if not self.git.exists() or not self.resolve_optional_ref(ACTIVE_REF):
            return []
        output, _ = self.git.run(
            "log",
            "--all",
            "--date=iso-strict",
            "--format=%H%x1f%aI%x1f%an%x1f%s",
            "-n",
            str(limit),
        )
        result = []
        for line in output.splitlines():
            fields = line.split("\x1f", 3)
            if len(fields) == 4:
                result.append(dict(zip(("commit", "time", "author", "message"), fields)))
        return result

    def raw_diff(self, left, right):
        left_sha = self.resolve_revision(left)
        right_sha = self.resolve_revision(right)
        output, _ = self.git.run("diff", "--no-ext-diff", left_sha, right_sha, "--", CONFIG_PATH)
        return output

    def parent_of_active(self):
        active = self.resolve_optional_ref(ACTIVE_REF)
        if not active:
            raise RepositoryError("active reference is not set")
        output, _ = self.git.run("rev-list", "--parents", "-n", "1", active)
        fields = output.split()
        if len(fields) < 2:
            raise RepositoryError("active commit is the baseline and has no parent")
        return fields[1]


def current_operator():
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        return sudo_user
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except (KeyError, OSError):
        return str(os.getuid())
