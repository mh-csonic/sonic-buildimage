from sonic_config_version.constants import STABLE_EXPORT_ATTEMPTS
from sonic_config_version.errors import ValidationError
from sonic_config_version.snapshot.normalizer import normalize_and_hash


class StableExporter:
    def __init__(self, adapter, attempts=STABLE_EXPORT_ATTEMPTS):
        self.adapter = adapter
        self.attempts = attempts

    def export(self):
        observed = {}
        for _ in range(self.attempts):
            normalized, snapshot_hash = normalize_and_hash(self.adapter.export_running())
            count = observed.get(snapshot_hash, (0, normalized))[0] + 1
            observed[snapshot_hash] = (count, normalized)
            if count >= 2:
                return normalized, snapshot_hash
        raise ValidationError(
            "running CONFIG_DB did not produce two matching exports in {} attempts".format(self.attempts)
        )
