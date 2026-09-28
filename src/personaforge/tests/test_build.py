import tempfile
import unittest
from pathlib import Path

from personaforge import BuildContractError, load_catalog, load_manifest, resolve_build_contract
from personaforge.build import render_makefile, validate_config_user, write_build_outputs


ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / "personaforge" / "profiles" / "l3-bgp-leaf-no-lag.yaml"
PROFILE_DIR = ROOT / "personaforge" / "profiles"
CATALOG = ROOT / "src" / "personaforge" / "catalogs" / "202605.yaml"
GENERATOR = ROOT / "scripts" / "personaforge-build"
SOURCE = "03a90ea321b3d9f71ae88ae23d4ccd146225e95c"


class BuildContractTest(unittest.TestCase):
    def contract(self):
        return resolve_build_contract(
            load_manifest(str(PROFILE)), load_catalog(str(CATALOG)), SOURCE, "vs", GENERATOR
        )

    def test_primary_profile_settings_are_catalog_limited(self):
        contract = self.contract()
        self.assertNotIn("BUILD_REDUCE_IMAGE_SIZE", contract.settings)
        self.assertEqual(contract.settings["INCLUDE_TEAMD"], "n")
        self.assertEqual(contract.settings["INCLUDE_LLDP"], "n")
        allowed = {
            component.get("buildVariable")
            for component in load_catalog(str(CATALOG)).document["components"].values()
            if component.get("buildVariable")
        }
        allowed.add("BUILD_REDUCE_IMAGE_SIZE")
        self.assertFalse(set(contract.settings) - allowed)

    def test_platform_independent_demo_profiles_use_standard_onie_archive_mode(self):
        catalog = load_catalog(str(CATALOG))
        for profile in sorted(PROFILE_DIR.glob("*.yaml")):
            with self.subTest(profile=profile.name):
                contract = resolve_build_contract(
                    load_manifest(str(profile)), catalog, SOURCE, "broadcom", GENERATOR
                )
                self.assertNotIn("BUILD_REDUCE_IMAGE_SIZE", contract.settings)

    def test_gnmi_and_telemetry_use_independent_baseline_controls(self):
        catalog = load_catalog(str(CATALOG))
        self.assertEqual(
            catalog.document["components"]["gnmi"]["buildVariable"],
            "INCLUDE_SYSTEM_GNMI",
        )
        self.assertEqual(
            catalog.document["components"]["telemetry"]["buildVariable"],
            "INCLUDE_SYSTEM_TELEMETRY",
        )

        bfd = resolve_build_contract(
            load_manifest(str(PROFILE_DIR / "l3-bgp-bfd-leaf.yaml")),
            catalog,
            SOURCE,
            "broadcom",
            GENERATOR,
        )
        self.assertEqual(bfd.settings["INCLUDE_SYSTEM_GNMI"], "n")
        self.assertEqual(bfd.settings["INCLUDE_SYSTEM_TELEMETRY"], "n")

        observable = resolve_build_contract(
            load_manifest(str(PROFILE_DIR / "l3-bgp-observability.yaml")),
            catalog,
            SOURCE,
            "broadcom",
            GENERATOR,
        )
        self.assertEqual(observable.settings["INCLUDE_SYSTEM_GNMI"], "y")
        self.assertEqual(observable.settings["INCLUDE_SYSTEM_TELEMETRY"], "y")

    def test_build_key_is_deterministic(self):
        first = self.contract()
        second = self.contract()
        self.assertEqual(first.build_key, second.build_key)

    def test_invalid_source_identity_is_rejected(self):
        manifest, catalog = load_manifest(str(PROFILE)), load_catalog(str(CATALOG))
        with self.assertRaises(BuildContractError):
            resolve_build_contract(manifest, catalog, "not-a-commit", "vs", GENERATOR)

    def test_any_valid_source_commit_is_recorded_in_identity(self):
        manifest, catalog = load_manifest(str(PROFILE)), load_catalog(str(CATALOG))
        alternate = "1" * 40
        contract = resolve_build_contract(manifest, catalog, alternate, "broadcom", GENERATOR)
        self.assertEqual(contract.plan["identity"]["sourceCommit"], alternate)

    def test_platform_is_not_restricted_but_remains_in_build_identity(self):
        manifest, catalog = load_manifest(str(PROFILE)), load_catalog(str(CATALOG))
        vs = resolve_build_contract(manifest, catalog, SOURCE, "vs", GENERATOR)
        broadcom = resolve_build_contract(manifest, catalog, SOURCE, "broadcom", GENERATOR)
        vendor_platform = resolve_build_contract(
            manifest, catalog, SOURCE, "x86_64-accton_as7726_32x-r0", GENERATOR
        )
        self.assertNotEqual(vs.build_key, broadcom.build_key)
        self.assertNotEqual(broadcom.build_key, vendor_platform.build_key)
        self.assertEqual(broadcom.plan["identity"]["platform"], "broadcom")

    def test_outputs_are_deterministic(self):
        contract = self.contract()
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            manifest, catalog = load_manifest(str(PROFILE)), load_catalog(str(CATALOG))
            write_build_outputs(Path(first), contract, manifest, catalog)
            write_build_outputs(Path(second), contract, manifest, catalog)
            for path in Path(first).iterdir():
                self.assertEqual(path.read_bytes(), (Path(second) / path.name).read_bytes())

    def test_makefile_has_conflict_guards_and_no_executable_make(self):
        content = render_makefile(self.contract())
        self.assertIn("$(origin INCLUDE_TEAMD)", content)
        self.assertNotIn("$(shell", content)
        self.assertNotIn("override ", content)
        self.assertNotIn("include ", content)

    def test_every_persona_build_setting_is_handed_to_slave_make(self):
        handoff = (ROOT / "Makefile.work").read_text(encoding="utf-8")
        catalog = load_catalog(str(CATALOG))
        variables = {
            component["buildVariable"]
            for component in catalog.document["components"].values()
            if component.get("buildVariable")
        }
        variables.add("BUILD_REDUCE_IMAGE_SIZE")
        for variable in sorted(variables):
            self.assertIn(
                "{}=$({})".format(variable, variable),
                handoff,
                "{} is not propagated to slave.mk".format(variable),
            )

    def test_conflicting_config_user_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.user"
            path.write_text("INCLUDE_TEAMD = y\n", encoding="utf-8")
            with self.assertRaises(BuildContractError):
                validate_config_user(path, self.contract().settings)

    def test_matching_config_user_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.user"
            path.write_text("INCLUDE_TEAMD = n\n", encoding="utf-8")
            validate_config_user(path, self.contract().settings)


if __name__ == "__main__":
    unittest.main()
