import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import click
from click.testing import CliRunner

from personaforge import RuntimeAction, RuntimePlan


ROOT = Path(__file__).resolve().parents[3]


class FakeConfigDB:
    def __init__(self):
        self.tables = {"FEATURE": {}, "FRR_DAEMON": {}}

    def get_table(self, table):
        return self.tables.get(table, {})

    def get_entry(self, table, key):
        return self.tables.get(table, {}).get(key, {})


class FakeValidatedConnector:
    def __init__(self, connector):
        self.connector = connector

    def mod_entry(self, table, key, value):
        self.connector.tables.setdefault(table, {}).setdefault(key, {}).update(value)

    def set_entry(self, table, key, value):
        if value is None:
            self.connector.tables.setdefault(table, {}).pop(key, None)
        else:
            self.connector.tables.setdefault(table, {})[key] = dict(value)


def load_module(name, path, injected):
    with patch.dict(sys.modules, injected):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class NativeCliCommandTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.common = types.ModuleType("utilities_common.personaforge")
        self.common.LIVE_METADATA_PATH = root / "run/active.json"
        self.common.PERSISTENT_METADATA_PATH = root / "var/active.json"
        self.common.SAVED_CONFIG_PATH = root / "etc/config_db.json"
        self.common.restart_bgp = MagicMock()
        self.common.save_config = MagicMock()
        self.database = FakeConfigDB()
        self.db_object = SimpleNamespace(cfgdb=self.database)

        def config_tables(config_db):
            return {name: config_db.get_table(name) for name in ("FEATURE", "FRR_DAEMON")}

        def verify_actions(config_db, actions):
            for action in actions:
                actual = (config_db.get_table(action.table).get(action.key) or {}).get(action.field)
                if actual != action.desired:
                    raise RuntimeError("verification failure")

        self.common.config_tables = config_tables
        self.common.verify_actions = verify_actions
        self.common.read_saved_tables = lambda: config_tables(self.database)
        self.plan = RuntimePlan(
            "demo", "a" * 64, "b" * 64,
            (RuntimeAction("FRR_DAEMON", "bfdd", "admin_status", "disabled", None, "test"),),
            True,
            True,
        )
        self.common.load_plan = lambda profile, config_db: self.plan

        utilities_package = types.ModuleType("utilities_common")
        utilities_package.__path__ = []
        utilities_package.personaforge = self.common
        cli_module = types.ModuleType("utilities_common.cli")
        cli_module.AbbreviationGroup = click.Group
        cli_module.pass_db = click.pass_obj
        config_package = types.ModuleType("config")
        config_package.__path__ = []
        show_package = types.ModuleType("show")
        show_package.__path__ = []
        validated_module = types.ModuleType("config.validated_config_db_connector")
        validated_module.ValidatedConfigDBConnector = FakeValidatedConnector
        tabulate_module = types.ModuleType("tabulate")
        tabulate_module.tabulate = lambda rows, headers=(), **kwargs: "\n".join(
            " ".join(str(value) for value in row) for row in rows
        )
        self.injected = {
            "utilities_common": utilities_package,
            "utilities_common.cli": cli_module,
            "utilities_common.personaforge": self.common,
            "config": config_package,
            "config.validated_config_db_connector": validated_module,
            "show": show_package,
            "tabulate": tabulate_module,
        }
        self.config_module = load_module(
            "config.personaforge",
            ROOT / "src/sonic-utilities/config/personaforge.py",
            self.injected,
        )
        self.show_module = load_module(
            "show.personaforge",
            ROOT / "src/sonic-utilities/show/personaforge.py",
            self.injected,
        )

    def test_apply_persist_and_deactivate_commands(self):
        runner = CliRunner()
        result = runner.invoke(
            self.config_module.personaforge,
            ["apply", "demo", "--persist", "--allow-disruptive", "-y"],
            obj=self.db_object,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(
            self.database.get_entry("FRR_DAEMON", "bfdd")["admin_status"], "disabled"
        )
        self.common.restart_bgp.assert_called_once()
        self.common.save_config.assert_called_once()
        metadata = json.loads(self.common.PERSISTENT_METADATA_PATH.read_text())
        self.assertTrue(metadata["persisted"])

        result = runner.invoke(
            self.config_module.personaforge,
            ["deactivate", "--persist", "--allow-disruptive", "-y"],
            obj=self.db_object,
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.database.get_entry("FRR_DAEMON", "bfdd"), {})
        self.assertFalse(self.common.PERSISTENT_METADATA_PATH.exists())

    def test_reapply_is_idempotent_and_different_profile_is_rejected(self):
        runner = CliRunner()
        command = ["apply", "demo", "--allow-disruptive", "-y"]
        first = runner.invoke(self.config_module.personaforge, command, obj=self.db_object)
        second = runner.invoke(self.config_module.personaforge, command, obj=self.db_object)
        self.assertEqual(first.exit_code, 0, first.output)
        self.assertEqual(second.exit_code, 0, second.output)
        self.common.restart_bgp.assert_called_once()

        other = RuntimePlan("other", "c" * 64, "b" * 64, self.plan.actions, True, True)
        self.common.load_plan = lambda profile, config_db: other
        rejected = runner.invoke(
            self.config_module.personaforge,
            ["apply", "other", "--allow-disruptive", "-y"], obj=self.db_object
        )
        self.assertNotEqual(rejected.exit_code, 0)
        self.assertIn("deactivate it before applying", rejected.output)

    def test_persist_refuses_drift(self):
        runner = CliRunner()
        applied = runner.invoke(
            self.config_module.personaforge,
            ["apply", "demo", "--allow-disruptive", "-y"], obj=self.db_object
        )
        self.assertEqual(applied.exit_code, 0, applied.output)
        self.database.tables["FRR_DAEMON"]["bfdd"]["admin_status"] = "enabled"
        persisted = runner.invoke(self.config_module.personaforge, ["persist", "-y"], obj=self.db_object)
        self.assertNotEqual(persisted.exit_code, 0)
        self.assertIn("drift", persisted.output)
        self.common.save_config.assert_not_called()

    def test_disruptive_apply_requires_explicit_authorization(self):
        result = CliRunner().invoke(
            self.config_module.personaforge, ["apply", "demo", "-y"], obj=self.db_object
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("--allow-disruptive", result.output)
        self.assertEqual(self.database.get_table("FRR_DAEMON"), {})

    def test_persisted_metadata_waits_for_saved_config_verification(self):
        self.common.read_saved_tables = lambda: {"FEATURE": {}, "FRR_DAEMON": {}}
        result = CliRunner().invoke(
            self.config_module.personaforge,
            ["apply", "demo", "--persist", "--allow-disruptive", "-y"],
            obj=self.db_object,
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("saved SONiC configuration", result.output)
        self.assertFalse(self.common.PERSISTENT_METADATA_PATH.exists())

    def test_show_plan_status_and_drift_commands(self):
        runner = CliRunner()
        planned = runner.invoke(
            self.show_module.personaforge, ["plan", "demo", "--json"], obj=self.db_object
        )
        self.assertEqual(planned.exit_code, 0, planned.output)
        self.assertEqual(json.loads(planned.output)["profile"], "demo")
        self.assertEqual(self.database.get_table("FRR_DAEMON"), {})

        applied = runner.invoke(
            self.config_module.personaforge,
            ["apply", "demo", "--allow-disruptive", "-y"], obj=self.db_object
        )
        self.assertEqual(applied.exit_code, 0, applied.output)
        status = runner.invoke(
            self.show_module.personaforge, ["status", "--json"], obj=self.db_object
        )
        self.assertEqual(status.exit_code, 0, status.output)
        self.assertEqual(json.loads(status.output)["drift"], [])
        converged = runner.invoke(
            self.show_module.personaforge, ["drift", "--json"], obj=self.db_object
        )
        self.assertEqual(converged.exit_code, 0, converged.output)
        self.assertEqual(json.loads(converged.output)["drift"], [])

        self.database.tables["FRR_DAEMON"]["bfdd"]["admin_status"] = "enabled"
        drifted = runner.invoke(
            self.show_module.personaforge, ["drift", "--json"], obj=self.db_object
        )
        self.assertEqual(drifted.exit_code, 0, drifted.output)
        self.assertEqual(json.loads(drifted.output)["drift"][0]["actual"], "enabled")


if __name__ == "__main__":
    unittest.main()
