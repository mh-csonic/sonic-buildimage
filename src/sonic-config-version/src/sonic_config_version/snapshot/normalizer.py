import hashlib
import json
import os
import stat

from sonic_config_version.constants import MAX_JSON_BYTES
from sonic_config_version.errors import ValidationError


def normalize(value):
    """Return deterministic compact UTF-8 JSON ending in exactly one newline."""
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError("invalid UTF-8 JSON: {}".format(exc))
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            raise ValidationError("invalid JSON: {}".format(exc))
    if not isinstance(value, dict):
        raise ValidationError("CONFIG_DB snapshot must be a JSON object")
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError("configuration cannot be normalized: {}".format(exc))
    return (rendered + "\n").encode("utf-8")


def digest(normalized):
    return hashlib.sha256(normalized).hexdigest()


def normalize_and_hash(value):
    normalized = normalize(value)
    return normalized, digest(normalized)


def read_json_file(path, max_bytes=MAX_JSON_BYTES):
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValidationError("cannot open {}: {}".format(path, exc))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValidationError("{} is not a regular file".format(path))
        if info.st_size > max_bytes:
            raise ValidationError("{} exceeds the {} byte limit".format(path, max_bytes))
        data = bytearray()
        while len(data) <= max_bytes:
            chunk = os.read(fd, min(65536, max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > max_bytes:
            raise ValidationError("{} exceeds the {} byte limit".format(path, max_bytes))
    finally:
        os.close(fd)
    return normalize(bytes(data))
