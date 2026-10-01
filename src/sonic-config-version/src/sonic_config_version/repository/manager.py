import json
import os
import pwd
import re

from sonic_config_version.constants import (
    ACTIVE_REF,
    CONFIG_PATH,
    LABEL_REF_PREFIX,
    METADATA_PATH,
    MIN_FREE_BYTES,
    MIN_FREE_INODES,
)
from sonic_config_version.errors import CommandError, NoChangeError, RepositoryError, ValidationError
from sonic_config_version.repository.git_runner import GitRunner, validate_revision
from sonic_config_version.snapshot.metadata import create_metadata, validate_metadata
from sonic_config_version.snapshot.normalizer import digest, normalize
from sonic_config_version.storage import Storage, has_strict_permissions


ZERO_SHA = "0" * 40
LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHA_LIKE_LABEL_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
RESERVED_LABELS = {"active", "head", "startup"}


def validate_label_name(label):
    if not isinstance(label, str) or not LABEL_PATTERN.fullmatch(label):
        raise ValidationError(
            "label must contain only lowercase letters, digits, '.', '_', or '-' and be at most 64 characters"
        )
    if label in RESERVED_LABELS:
        raise ValidationError("label {!r} is reserved".format(label))
    if SHA_LIKE_LABEL_PATTERN.fullmatch(label):
        raise ValidationError("label must not look like an abbreviated commit SHA")
    return label


def label_ref(label):
    return LABEL_REF_PREFIX + validate_label_name(label)


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

    def worktree_status(self):
        if not self.git.exists():
            return "NOT_INITIALIZED"
        output, _ = self.git.run("status", "--porcelain")
        return "DIRTY" if output.strip() else "CLEAN"

    def resolve_optional_ref(self, reference):
        if not self.git.exists():
            return None
        output, _ = self.git.run("rev-parse", "--verify", "--quiet", reference, check=False)
        candidate = output.strip()
        return candidate if len(candidate) == 40 else None

    def resolve_revision(self, revision):
        validate_revision(revision)
        reference = revision
        try:
            candidate_ref = label_ref(revision)
        except ValidationError:
            candidate_ref = None
        if candidate_ref and self.resolve_optional_ref(candidate_ref):
            reference = candidate_ref
        try:
            output, _ = self.git.run("rev-parse", "--verify", "{}^{{commit}}".format(reference))
        except CommandError:
            raise RepositoryError("revision {!r} was not found".format(revision))
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

    def list_labels(self):
        if not self.git.exists():
            return []
        output, _ = self.git.run(
            "for-each-ref",
            "--format=%(refname:strip=2)",
            LABEL_REF_PREFIX,
        )
        result = []
        for name in output.splitlines():
            name = name.strip()
            if not name:
                continue
            try:
                validate_label_name(name)
                sha = self.resolve_revision(name)
            except (RepositoryError, ValidationError):
                continue
            result.append({"label": name, "commit": sha})
        return result

    def labels_for_revision(self, revision):
        sha = self.resolve_revision(revision)
        return [entry["label"] for entry in self.list_labels() if entry["commit"] == sha]

    def create_label(self, label, revision):
        reference = label_ref(label)
        sha = self.resolve_revision(revision)
        existing = self.resolve_optional_ref(reference)
        if existing:
            raise RepositoryError(
                "label {!r} already exists at {}; requested target was {}".format(label, existing, sha)
            )
        assigned_labels = self.labels_for_revision(sha)
        if assigned_labels:
            raise RepositoryError(
                "commit {} already has label {}; delete it before assigning {!r}".format(
                    sha,
                    ", ".join(repr(item) for item in assigned_labels),
                    label,
                )
            )
        self.git.run("update-ref", reference, sha, ZERO_SHA)
        self._tighten_modes()
        return sha

    def delete_label(self, label):
        reference = label_ref(label)
        sha = self.resolve_optional_ref(reference)
        if not sha:
            raise RepositoryError("label {!r} does not exist".format(label))
        self.git.run("update-ref", "-d", reference, sha)
        self._tighten_modes()
        return sha

    def commit_snapshot(self, normalized, snapshot_hash, message, operator, system_info, allow_empty=False, label=None):
        current = self.resolve_optional_ref(ACTIVE_REF)
        old_head = self.resolve_optional_ref("HEAD")
        new_label_ref = label_ref(label) if label is not None else None
        existing_label_sha = self.resolve_optional_ref(new_label_ref) if new_label_ref else None
        if existing_label_sha:
            raise RepositoryError("label {!r} already exists at {}".format(label, existing_label_sha))
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
        if new_label_ref:
            assigned_labels = self.labels_for_revision(sha)
            if assigned_labels:
                self._restore_worktree(old_head)
                raise RepositoryError(
                    "commit {} already has label {}; cannot assign {!r}".format(
                        sha,
                        ", ".join(repr(item) for item in assigned_labels),
                        label,
                    )
                )
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
        if new_label_ref:
            commands.append("create {} {}".format(new_label_ref, sha))
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
                entry = dict(zip(("commit", "time", "author", "message"), fields))
                _, metadata = self.load_snapshot(entry["commit"])
                entry["operator"] = metadata["operator"]
                entry["labels"] = self.labels_for_revision(entry["commit"])
                result.append(entry)
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
