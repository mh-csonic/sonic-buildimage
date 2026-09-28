import json
import tempfile
import unittest
from pathlib import Path

from personaforge import (
    RuntimeAction,
    RuntimeContractError,
    calculate_drift,
    create_active_metadata,
    inverse_actions,
    load_catalog,
    load_manifest,
    read_metadata,
    resolve_profile_path,
    resolve_runtime_plan,
)
from personaforge.runtime import atomic_write_json


ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / "personaforge/profiles/l3-bgp-leaf-no-lag.yaml"
CATALOG = ROOT / "src/personaforge/catalogs/202605.yaml"


class RuntimeContractTest(unittest.TestCase):
    def plan(self, tables=None):
        return resolve_runtime_plan(
            load_manifest(str(PROFILE)),
            load_catalog(str(CATALOG)),
            tables or {"FEATURE": {}, "FRR_DAEMON": {}},
        )

    def test_profile_resolves_frr_and_existing_features(self):
        tables = {
            "FEATURE": {
                "teamd": {"state": "enabled"},
                "lldp": {"state": "enabled"},
            },
            "FRR_DAEMON": {},
        }
        actions = {(item.table, item.key): item for item in self.plan(tables).actions}
        self.assertEqual(actions[("FEATURE", "teamd")].desired, "disabled")
        self.assertEqual(actions[("FEATURE", "lldp")].desired, "disabled")
        self.assertEqual(actions[("FRR_DAEMON", "bfdd")].desired, "disabled")

    def test_build_pruned_feature_is_not_recreated(self):
        actions = self.plan().actions
        self.assertEqual([(item.table, item.key) for item in actions], [("FRR_DAEMON", "bfdd")])

    def test_inverse_restores_previous_values_and_deletes_new_rows(self):
        plan = self.plan({"FEATURE": {}, "FRR_DAEMON": {}})
        metadata = create_active_metadata(plan, False)
        inverse = inverse_actions(metadata)
        self.assertEqual(len(inverse), 1)
        self.assertIsNone(inverse[0].desired)
        self.assertEqual(inverse[0].previous, "disabled")

    def test_drift_reports_missing_or_changed_values(self):
        metadata = create_active_metadata(self.plan(), False)
        drift = calculate_drift(metadata, {"FRR_DAEMON": {}})
        self.assertEqual(drift[0]["key"], "bfdd")
        self.assertEqual(drift[0]["desired"], "disabled")
        self.assertEqual(calculate_drift(metadata, {
            "FRR_DAEMON": {"bfdd": {"admin_status": "disabled"}}
        }), [])

    def test_metadata_is_atomic_and_prefers_live_path(self):
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory) / "run/active.json"
            persisted = Path(directory) / "var/active.json"
            atomic_write_json(persisted, {"schemaVersion": 1, "profile": "persisted"})
            atomic_write_json(live, {"schemaVersion": 1, "profile": "live"})
            document, source = read_metadata((live, persisted))
            self.assertEqual(document["profile"], "live")
            self.assertEqual(source, live)

    def test_profile_resolution_is_name_bounded(self):
        self.assertEqual(resolve_profile_path("l3-bgp-leaf-no-lag", (PROFILE.parent,)), PROFILE)
        with self.assertRaises(RuntimeContractError):
            resolve_profile_path("../outside", (PROFILE.parent,))


if __name__ == "__main__":
    unittest.main()
