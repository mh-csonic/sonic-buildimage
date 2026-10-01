import contextlib
import json
import os
import shutil
import stat
import tempfile

from sonic_config_version.constants import (
    AUDIT_RELATIVE_PATH,
    CHECKPOINT_METADATA_DIRNAME,
    OPERATION_LOCK_RELATIVE_PATH,
    REPOSITORY_DIRNAME,
    TMP_DIRNAME,
)
from sonic_config_version.errors import StorageError


class Storage:
    def __init__(self, base_dir):
        self.base_dir = os.path.abspath(base_dir)
        self.repository = os.path.join(self.base_dir, REPOSITORY_DIRNAME)
        self.tmp_dir = os.path.join(self.base_dir, TMP_DIRNAME)
        self.audit_path = os.path.join(self.base_dir, AUDIT_RELATIVE_PATH)
        self.operation_lock_path = os.path.join(self.base_dir, OPERATION_LOCK_RELATIVE_PATH)
        self.checkpoint_metadata_dir = os.path.join(self.base_dir, CHECKPOINT_METADATA_DIRNAME)

    def _ensure_directory(self, path):
        current = os.path.sep
        for component in os.path.abspath(path).split(os.path.sep)[1:]:
            current = os.path.join(current, component)
            if os.path.lexists(current) and os.path.islink(current):
                raise StorageError("refusing symlink in storage path: {}".format(current))
        os.makedirs(path, mode=0o700, exist_ok=True)
        os.chmod(path, 0o700)

    def ensure_layout(self):
        for path in (
            self.base_dir,
            self.repository,
            self.tmp_dir,
            os.path.dirname(self.audit_path),
            os.path.dirname(self.operation_lock_path),
            self.checkpoint_metadata_dir,
        ):
            self._ensure_directory(path)

    def check_capacity(self, min_bytes, min_inodes):
        try:
            usage = shutil.disk_usage(self.base_dir)
            vfs = os.statvfs(self.base_dir)
        except OSError as exc:
            raise StorageError("cannot inspect storage capacity: {}".format(exc))
        if usage.free < min_bytes:
            raise StorageError("insufficient free space for SonicGit operation")
        if vfs.f_favail < min_inodes:
            raise StorageError("insufficient free inodes for SonicGit operation")

    @contextlib.contextmanager
    def private_candidate(self, content):
        self._ensure_directory(self.tmp_dir)
        fd, path = tempfile.mkstemp(prefix="candidate-", suffix=".json", dir=self.tmp_dir)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            yield path
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    def write_checkpoint_metadata(self, operation_id, metadata):
        directory = os.path.join(self.checkpoint_metadata_dir, operation_id)
        self._ensure_directory(directory)
        self.atomic_write_json(os.path.join(directory, "metadata.json"), metadata)

    @staticmethod
    def atomic_write(path, content, mode=0o600):
        parent = os.path.dirname(path)
        os.makedirs(parent, mode=0o700, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".sonicgit-", dir=parent)
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def atomic_write_json(cls, path, value):
        content = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        cls.atomic_write(path, content)


def has_strict_permissions(path, required_uid=None):
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise StorageError("cannot stat {}: {}".format(path, exc))
    if stat.S_ISLNK(info.st_mode):
        raise StorageError("refusing symlink: {}".format(path))
    if required_uid is not None and info.st_uid != required_uid:
        raise StorageError("{} is not owned by uid {}".format(path, required_uid))
    if info.st_mode & 0o077:
        raise StorageError("{} must not be accessible by group or other users".format(path))
    return True
