from sonic_config_version.errors import ValidationError
from sonic_config_version.snapshot.normalizer import normalize_and_hash


def verify_checkpoint(adapter, name, expected_hash):
    _, checkpoint_hash = normalize_and_hash(adapter.read_checkpoint(name))
    if checkpoint_hash != expected_hash:
        raise ValidationError("native checkpoint does not match pre-operation running configuration")
    return checkpoint_hash
