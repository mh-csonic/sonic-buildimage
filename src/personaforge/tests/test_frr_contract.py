import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jinja2 import Environment


ROOT = Path(__file__).resolve().parents[3]
SUPERVISOR_TEMPLATE = ROOT / "dockers/docker-fpm-frr/frr/supervisord/supervisord.conf.j2"
CRITICAL_TEMPLATE = ROOT / "dockers/docker-fpm-frr/frr/supervisord/critical_processes.j2"
YANG_MODEL = ROOT / "src/sonic-yang-models/yang-models/sonic-frr-daemon.yang"
YANG_SAMPLE_CONFIG = ROOT / "src/sonic-yang-models/tests/files/sample_config_db.json"


def render(path, frr_daemon=None, software_bfd=False):
    context = {
        "DEVICE_METADATA": {"localhost": {"frr_mgmt_framework_config": "true"}},
        "FEATURE": {},
        "SYSTEM_DEFAULTS": {
            "software_bfd": {"status": "enabled" if software_bfd else "disabled"}
        },
        "WARM_RESTART": {},
    }
    if frr_daemon is not None:
        context["FRR_DAEMON"] = frr_daemon
    return Environment(keep_trailing_newline=True).from_string(
        path.read_text(encoding="utf-8")
    ).render(**context)


class FrrTemplateContractTest(unittest.TestCase):
    optional_daemons = ("bfdd", "ospfd", "pimd", "pathd")

    def assert_programs_present(self, content, daemons):
        for daemon in daemons:
            self.assertIn("program:{}".format(daemon), content)

    def assert_programs_absent(self, content, daemons):
        for daemon in daemons:
            self.assertNotIn("program:{}".format(daemon), content)

    def test_missing_table_preserves_management_mode_defaults(self):
        self.assert_programs_present(render(SUPERVISOR_TEMPLATE), self.optional_daemons)
        self.assert_programs_present(render(CRITICAL_TEMPLATE), self.optional_daemons)

    def test_disabled_optional_daemons_are_not_rendered(self):
        disabled = {name: {"admin_status": "disabled"} for name in self.optional_daemons}
        supervisor = render(SUPERVISOR_TEMPLATE, disabled, software_bfd=True)
        critical = render(CRITICAL_TEMPLATE, disabled)
        self.assert_programs_absent(supervisor, self.optional_daemons)
        self.assert_programs_absent(critical, self.optional_daemons)
        self.assertNotIn("program:bfdmon", supervisor)
        self.assert_programs_present(supervisor, ("zebra", "staticd", "bgpd", "fpmsyncd", "frrcfgd"))
        self.assert_programs_present(critical, ("zebra", "staticd", "bgpd", "fpmsyncd", "frrcfgd"))

    def test_default_and_enabled_states_preserve_daemons(self):
        states = {
            "bfdd": {"admin_status": "default"},
            "ospfd": {"admin_status": "enabled"},
            "pimd": {},
        }
        self.assert_programs_present(render(SUPERVISOR_TEMPLATE, states), self.optional_daemons)


class FrrCfgdContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        swsscommon_package = types.ModuleType("swsscommon")
        swsscommon_module = types.ModuleType("swsscommon.swsscommon")
        swsscommon_module.ConfigDBConnector = MagicMock
        swsscommon_package.swsscommon = swsscommon_module
        netaddr_module = types.ModuleType("netaddr")
        cls.module_patches = patch.dict(sys.modules, {
            "netaddr": netaddr_module,
            "swsscommon": swsscommon_package,
            "swsscommon.swsscommon": swsscommon_module,
        })
        cls.module_patches.start()
        spec = importlib.util.spec_from_file_location(
            "personaforge_test_frrcfgd",
            ROOT / "src/sonic-frr-mgmt-framework/frrcfgd/frrcfgd.py",
        )
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    @classmethod
    def tearDownClass(cls):
        cls.module_patches.stop()

    def test_config_db_only_disables_allowlisted_explicit_rows(self):
        database = MagicMock()
        database.get_table.return_value = {
            "bfdd": {"admin_status": "disabled"},
            "ospfd": {"admin_status": "default"},
            "zebra": {"admin_status": "disabled"},
        }
        self.assertEqual(self.module.get_disabled_frr_daemons(database), {"bfdd"})

    def test_missing_table_preserves_default_set(self):
        database = MagicMock()
        database.get_table.return_value = None
        self.assertEqual(self.module.get_disabled_frr_daemons(database), set())

    def test_client_set_filters_optional_daemons_and_rejects_protected(self):
        manager_class = self.module.BgpdClientMgr
        with patch.object(manager_class, "_BgpdClientMgr__create_frr_client", return_value=True), \
             patch.object(manager_class, "_BgpdClientMgr__create_proxy_socket", return_value=MagicMock()):
            manager = manager_class({"bfdd", "pathd"})
            self.assertNotIn("bfdd", manager.enabled_daemons)
            self.assertNotIn("pathd", manager.enabled_daemons)
            self.assertIn("zebra", manager.enabled_daemons)
            with self.assertRaises(ValueError):
                manager_class({"zebra"})


class ClassicBfdContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package = types.ModuleType("bgpcfgd")
        package.__path__ = []
        log_module = types.ModuleType("bgpcfgd.log")
        for name in ("log_warn", "log_err", "log_info", "log_crit"):
            setattr(log_module, name, MagicMock())
        manager_module = types.ModuleType("bgpcfgd.manager")
        manager_module.Manager = object
        utils_module = types.ModuleType("bgpcfgd.utils")
        utils_module.run_command = MagicMock()
        cls.module_patches = patch.dict(sys.modules, {
            "bgpcfgd": package,
            "bgpcfgd.log": log_module,
            "bgpcfgd.manager": manager_module,
            "bgpcfgd.utils": utils_module,
        })
        cls.module_patches.start()
        spec = importlib.util.spec_from_file_location(
            "bgpcfgd.managers_bfd",
            ROOT / "src/sonic-bgpcfgd/bgpcfgd/managers_bfd.py",
        )
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    @classmethod
    def tearDownClass(cls):
        cls.module_patches.stop()

    def test_disabled_bfdd_cannot_be_spawned(self):
        manager = self.module.BfdMgr.__new__(self.module.BfdMgr)
        manager.daemon_enabled = False
        with patch.object(self.module.subprocess, "check_output") as check, \
             patch.object(self.module.subprocess, "run") as run:
            self.assertFalse(manager.check_and_start_bfdd())
            check.assert_not_called()
            run.assert_not_called()


class FrrYangContractTest(unittest.TestCase):
    def test_yang_model_is_packaged_and_allowlisted(self):
        model = YANG_MODEL.read_text(encoding="utf-8")
        for daemon in ("bfdd", "ospfd", "pimd", "pathd"):
            self.assertIn("enum {};".format(daemon), model)
        for state in ("default", "enabled", "disabled"):
            self.assertIn("enum {};".format(state), model)
        self.assertIn("'sonic-frr-daemon.yang'", (ROOT / "src/sonic-yang-models/setup.py").read_text())

    def test_yang_sample_config_contains_frr_daemon_table(self):
        sample = json.loads(YANG_SAMPLE_CONFIG.read_text(encoding="utf-8"))["SAMPLE_CONFIG_DB_JSON"]
        self.assertEqual(sample["FRR_DAEMON"]["bfdd"]["admin_status"], "disabled")


if __name__ == "__main__":
    unittest.main()
