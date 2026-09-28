import json
import tempfile
import unittest
from pathlib import Path

from personaforge import CatalogError, ManifestError, load_catalog, load_manifest, validate_manifest_against_catalog


ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / "personaforge" / "profiles" / "l3-bgp-leaf-no-lag.yaml"
PROFILE_DIR = ROOT / "personaforge" / "profiles"
CATALOG = ROOT / "src" / "personaforge" / "catalogs" / "202605.yaml"


class ContractTest(unittest.TestCase):
    def write(self, text):
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".yaml", delete=False)
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        handle.write(text)
        handle.close()
        return handle.name

    def test_primary_profile_and_catalog(self):
        manifest = load_manifest(str(PROFILE))
        catalog = load_catalog(str(CATALOG))
        validate_manifest_against_catalog(manifest, catalog)
        self.assertEqual(manifest.name, "l3-bgp-leaf-no-lag")
        self.assertEqual(len(manifest.sha256), 64)
        self.assertEqual(json.loads(manifest.canonical_json)["build"]["reduceFilesystem"], True)
        self.assertEqual(catalog.document["components"]["bfdd"]["implementationStatus"], "implemented")
        self.assertNotIn("platforms", manifest.document["compatibility"])
        self.assertNotIn("maxAsics", manifest.document["compatibility"])
        self.assertNotIn("platforms", catalog.document)
        self.assertNotIn("maxAsics", catalog.document)
        self.assertNotIn("sourceCommit", catalog.document)

    def test_all_shipped_profiles_validate_against_catalog(self):
        catalog = load_catalog(str(CATALOG))
        expected = {
            "l3-bgp-bfd-leaf",
            "l3-bgp-leaf-no-lag",
            "l3-bgp-observability",
            "l3-multirouting-lab",
        }
        found = set()
        for path in sorted(PROFILE_DIR.glob("*.yaml")):
            manifest = load_manifest(str(path))
            validate_manifest_against_catalog(manifest, catalog)
            self.assertEqual(manifest.name, path.stem)
            found.add(manifest.name)
        self.assertEqual(found, expected)

    def test_demo_profiles_exercise_distinct_runtime_controls(self):
        bfd = load_manifest(str(PROFILE_DIR / "l3-bgp-bfd-leaf.yaml"))
        routing = load_manifest(str(PROFILE_DIR / "l3-multirouting-lab.yaml"))
        observable = load_manifest(str(PROFILE_DIR / "l3-bgp-observability.yaml"))
        self.assertEqual(bfd.document["overrides"]["frrDaemons"]["bfdd"], "enabled")
        self.assertEqual(
            set(routing.document["overrides"]["frrDaemons"]),
            {"bfdd", "ospfd", "pimd", "pathd"},
        )
        self.assertEqual(
            set(observable.document["overrides"]["features"]),
            {"lldp", "sflow", "snmp", "gnmi", "telemetry"},
        )

    def test_canonical_digest_ignores_map_and_set_order(self):
        original = PROFILE.read_text(encoding="utf-8")
        reordered = original.replace(
            "require: [l3-forwarding, bgp, ssh-cli, platform-monitoring]",
            "require: [platform-monitoring, ssh-cli, bgp, l3-forwarding]",
        )
        self.assertEqual(load_manifest(str(PROFILE)).sha256, load_manifest(self.write(reordered)).sha256)

    def test_rejects_duplicate_key(self):
        text = PROFILE.read_text(encoding="utf-8").replace(
            "  persistRuntime: true", "  persistRuntime: true\n  persistRuntime: false"
        )
        with self.assertRaisesRegex(ManifestError, "duplicate key"):
            load_manifest(self.write(text))

    def test_rejects_unknown_field(self):
        text = PROFILE.read_text(encoding="utf-8") + "unknown: true\n"
        with self.assertRaises(ManifestError):
            load_manifest(self.write(text))

    def test_rejects_invalid_type_and_enum(self):
        text = PROFILE.read_text(encoding="utf-8").replace(
            "allowDisruptive: true", "allowDisruptive: yes-please"
        ).replace("lldp: disabled", "lldp: stopped")
        with self.assertRaises(ManifestError):
            load_manifest(self.write(text))

    def test_rejects_custom_yaml_tag(self):
        text = PROFILE.read_text(encoding="utf-8").replace(
            "description: Lab leaf", "description: !unsafe Lab leaf"
        )
        with self.assertRaises(ManifestError):
            load_manifest(self.write(text))

    def test_rejects_require_omit_overlap(self):
        text = PROFILE.read_text(encoding="utf-8").replace(
            "omit: [link-aggregation", "omit: [bgp, link-aggregation"
        )
        with self.assertRaisesRegex(ManifestError, "both require and omit"):
            load_manifest(self.write(text))

    def test_rejects_unknown_catalog_feature(self):
        text = PROFILE.read_text(encoding="utf-8").replace("lldp: disabled", "invented: disabled")
        with self.assertRaisesRegex(ManifestError, "feature overrides"):
            validate_manifest_against_catalog(load_manifest(self.write(text)), load_catalog(str(CATALOG)))

    def test_rejects_non_allowlisted_catalog_daemon(self):
        text = CATALOG.read_text(encoding="utf-8").replace("daemonName: bfdd", "daemonName: bgpd")
        with self.assertRaises(CatalogError):
            load_catalog(self.write(text))

    def test_catalog_build_variables_exist_on_baseline(self):
        catalog = load_catalog(str(CATALOG))
        make_config = (ROOT / "rules" / "config").read_text(encoding="utf-8")
        for component in catalog.document["components"].values():
            variable = component.get("buildVariable")
            if variable:
                self.assertRegex(make_config, r"(?m)^{}\s*[?:+]?=".format(variable))

    def test_normalized_document_is_immutable(self):
        manifest = load_manifest(str(PROFILE))
        with self.assertRaises(TypeError):
            manifest.document["kind"] = "Other"


if __name__ == "__main__":
    unittest.main()
