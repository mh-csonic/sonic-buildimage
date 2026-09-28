import fcntl
import os

from sonic_config_version.errors import LockError


class FileLock:
    def __init__(self, path, label="operation", create_parent=True):
        self.path = path
        self.label = label
        self.create_parent = create_parent
        self.fd = None

    def __enter__(self):
        if self.create_parent:
            os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            self.fd = os.open(self.path, flags, 0o600)
            os.fchmod(self.fd, 0o600)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(self.fd, 0)
            os.write(self.fd, "{}, pid {}\n".format(self.label, os.getpid()).encode())
            os.fsync(self.fd)
        except (OSError, IOError) as exc:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            raise LockError("cannot acquire {} lock {}: {}".format(self.label, self.path, exc))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.fd is not None:
            try:
                os.ftruncate(self.fd, 0)
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None
