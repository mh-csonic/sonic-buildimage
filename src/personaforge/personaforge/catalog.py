import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft4Validator

from ._yaml import load_yaml
from .errors import CatalogError, ManifestError
from .manifest import NormalizedManifest


_ROOT = Path(__file__).resolve().parent.parent
_SOURCE_CATALOG_SCHEMA_PATH = _ROOT / "schema" / "catalog-v1.json"
DEFAULT_CATALOG_SCHEMA_PATH = (
    _SOURCE_CATALOG_SCHEMA_PATH
    if _SOURCE_CATALOG_SCHEMA_PATH.exists()
    else Path("/usr/share/personaforge/schema/catalog-v1.json")
)
FRR_DAEMON_ALLOWLIST = frozenset(("bfdd", "ospfd", "pimd", "pathd"))


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class ReleaseCatalog:
    document: Mapping[str, Any]
    canonical_json: bytes
    sha256: str
    source: str

    @property
    def sonic_release(self) -> str:
        return self.document["sonicRelease"]


def load_catalog(path: str, schema_path: str = None) -> ReleaseCatalog:
    source_path = Path(path)
    schema_file = Path(schema_path) if schema_path else DEFAULT_CATALOG_SCHEMA_PATH
    document = load_yaml(source_path, CatalogError)
    if not isinstance(document, dict):
        raise CatalogError("catalog root must be a mapping")
    try:
        with schema_file.open("r", encoding="utf-8") as stream:
            schema = json.load(stream)
    except (OSError, ValueError) as exc:
        raise CatalogError("unable to load catalog schema {}: {}".format(schema_file, exc)) from exc

    try:
        Draft4Validator.check_schema(schema)
    except Exception as exc:
        raise CatalogError("invalid catalog schema {}: {}".format(schema_file, exc)) from exc
    errors = sorted(Draft4Validator(schema).iter_errors(document), key=lambda item: list(item.absolute_path))
    if errors:
        rendered = []
        for error in errors:
            location = ".".join(str(part) for part in error.absolute_path) or "$"
            rendered.append("{}: {}".format(location, error.message))
        raise CatalogError("; ".join(rendered))

    components = document["components"]
    for capability, component_names in document["capabilities"].items():
        missing = sorted(set(component_names) - set(components))
        if missing:
            raise CatalogError("capability {} references unknown components: {}".format(capability, ", ".join(missing)))
    for name, component in components.items():
        adapter = component["runtimeAdapter"]
        if adapter == "feature" and "featureName" not in component:
            raise CatalogError("feature component {} has no featureName".format(name))
        if adapter == "frr-daemon":
            daemon = component.get("daemonName")
            if daemon not in FRR_DAEMON_ALLOWLIST:
                raise CatalogError("component {} uses non-allowlisted FRR daemon {!r}".format(name, daemon))

    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return ReleaseCatalog(
        document=_freeze(document),
        canonical_json=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
        source=str(source_path),
    )


def validate_manifest_against_catalog(manifest: NormalizedManifest, catalog: ReleaseCatalog) -> None:
    data = manifest.document
    if data["compatibility"]["sonicRelease"] != catalog.sonic_release:
        raise ManifestError("manifest release does not match catalog release")

    known_capabilities = set(catalog.document["capabilities"])
    requested_capabilities = set(data["capabilities"]["require"]) | set(data["capabilities"]["omit"])
    unknown_capabilities = sorted(requested_capabilities - known_capabilities)
    if unknown_capabilities:
        raise ManifestError("catalog does not define capabilities: {}".format(", ".join(unknown_capabilities)))

    components = catalog.document["components"]
    known_features = {
        component["featureName"]
        for component in components.values()
        if component["runtimeAdapter"] == "feature"
    }
    unknown_features = sorted(set(data["overrides"]["features"]) - known_features)
    if unknown_features:
        raise ManifestError("catalog does not define feature overrides: {}".format(", ".join(unknown_features)))

    known_daemons = {
        component["daemonName"]
        for component in components.values()
        if component["runtimeAdapter"] == "frr-daemon"
    }
    unknown_daemons = sorted(set(data["overrides"]["frrDaemons"]) - known_daemons)
    if unknown_daemons:
        raise ManifestError("catalog does not define FRR daemon overrides: {}".format(", ".join(unknown_daemons)))

    protected = set()
    for capability in data["capabilities"]["require"]:
        protected.update(catalog.document["capabilities"][capability])
    for component_name in protected:
        component = components[component_name]
        if component["runtimeAdapter"] == "feature":
            override = data["overrides"]["features"].get(component["featureName"])
        elif component["runtimeAdapter"] == "frr-daemon":
            override = data["overrides"]["frrDaemons"].get(component["daemonName"])
        else:
            override = None
        if override == "disabled":
            raise ManifestError("override disables component required by a capability: {}".format(component_name))
