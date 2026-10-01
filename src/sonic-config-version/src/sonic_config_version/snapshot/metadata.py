from datetime import datetime, timezone
import re

from sonic_config_version.constants import NORMALIZATION_VERSION
from sonic_config_version.errors import ValidationError


REQUIRED_FIELDS = {
    "schema_version",
    "normalization_version",
    "configuration_sha256",
    "created_at",
    "operator",
    "message",
    "source",
    "platform",
    "hwsku",
    "sonic_release",
    "asic_count",
    "parent",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def create_metadata(snapshot_hash, operator, message, system_info, parent):
    return {
        "schema_version": 1,
        "normalization_version": NORMALIZATION_VERSION,
        "configuration_sha256": snapshot_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator": operator,
        "message": message,
        "source": "running CONFIG_DB",
        "platform": system_info.get("platform"),
        "hwsku": system_info.get("hwsku"),
        "sonic_release": system_info.get("sonic_release"),
        "asic_count": system_info.get("asic_count"),
        "parent": parent,
    }


def validate_metadata(metadata, snapshot_hash):
    if not isinstance(metadata, dict):
        raise ValidationError("metadata/version.json must be a JSON object")
    missing = REQUIRED_FIELDS - set(metadata)
    if missing:
        raise ValidationError("commit metadata is missing: {}".format(", ".join(sorted(missing))))
    if type(metadata["schema_version"]) is not int or metadata["schema_version"] != 1:
        raise ValidationError("unsupported metadata schema")
    if type(metadata["normalization_version"]) is not int or metadata["normalization_version"] != NORMALIZATION_VERSION:
        raise ValidationError("unsupported normalization version")
    if metadata["configuration_sha256"] != snapshot_hash:
        raise ValidationError("commit configuration checksum does not match metadata")
    if not SHA256_PATTERN.fullmatch(metadata["configuration_sha256"]):
        raise ValidationError("invalid configuration checksum in metadata")
    if metadata["source"] != "running CONFIG_DB":
        raise ValidationError("unsupported snapshot source in metadata")
    if type(metadata["asic_count"]) is not int or metadata["asic_count"] != 1:
        raise ValidationError("commit metadata is not single-ASIC")
    for field in ("created_at", "operator", "message", "platform", "hwsku", "sonic_release"):
        if not isinstance(metadata[field], str) or not metadata[field]:
            raise ValidationError("commit metadata field {} must be a non-empty string".format(field))
    parent = metadata["parent"]
    if parent is not None and (not isinstance(parent, str) or not COMMIT_PATTERN.fullmatch(parent)):
        raise ValidationError("invalid parent commit in metadata")
