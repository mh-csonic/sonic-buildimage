import json
import os
import re
import stat
from datetime import datetime, timezone

from sonic_config_version.errors import StorageError


SENSITIVE_FRAGMENTS = ("password", "passwd", "secret", "token", "community", "private_key", "passkey")
SENSITIVE_TEXT = re.compile(
    r"(?i)(password|passwd|secret|token|community|private[_-]?key|passkey)(\s*[:=]\s*)([^\s,}\]]+|\"[^\"]*\")"
)


def redact(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            result[key] = "<redacted>" if any(part in lowered for part in SENSITIVE_FRAGMENTS) else redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_TEXT.sub(r"\1\2<redacted>", value)
    return value


class AuditLog:
    def __init__(self, path):
        self.path = path

    def append(self, action, result, **details):
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "result": result,
            "details": redact(details),
        }
        payload = (json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.path, flags, 0o600)
            os.fchmod(fd, 0o600)
            try:
                os.write(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise StorageError("cannot append audit event: {}".format(exc))

    def read(self, limit=20):
        if not os.path.exists(self.path):
            return []
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.path, flags)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):
                    raise StorageError("audit path is not a regular file")
                max_read = 16 * 1024 * 1024
                if info.st_size > max_read:
                    os.lseek(fd, info.st_size - max_read, os.SEEK_SET)
                payload = bytearray()
                while len(payload) <= max_read:
                    chunk = os.read(fd, min(65536, max_read + 1 - len(payload)))
                    if not chunk:
                        break
                    payload.extend(chunk)
            finally:
                os.close(fd)
        except OSError as exc:
            raise StorageError("cannot read audit log: {}".format(exc))
        text = bytes(payload[:max_read]).decode("utf-8", "replace")
        lines = text.splitlines()
        if info.st_size > max_read and lines:
            lines = lines[1:]
        events = []
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line))
            except ValueError:
                events.append({"result": "corrupt", "raw": "<invalid audit record>"})
        return events
