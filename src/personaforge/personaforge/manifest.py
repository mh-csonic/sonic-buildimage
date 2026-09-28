import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Tuple

from jsonschema import Draft4Validator

from ._yaml import load_yaml
from .errors import ManifestError


_ROOT = Path(__file__).resolve().parent.parent
_SOURCE_SCHEMA_PATH = _ROOT / "schema" / "persona-v1alpha1.json"
DEFAULT_SCHEMA_PATH = (
    _SOURCE_SCHEMA_PATH
    if _SOURCE_SCHEMA_PATH.exists()
    else Path("/usr/share/personaforge/schema/persona-v1alpha1.json")
)


def _format_errors(validator: Draft4Validator, value: Any) -> str:
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path))
    rendered = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        rendered.append("{}: {}".format(location, error.message))
    return "; ".join(rendered)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _normalize(document: dict) -> dict:
    normalized = copy.deepcopy(document)
    normalized.setdefault("overrides", {})
    normalized["overrides"].setdefault("features", {})
    normalized["overrides"].setdefault("frrDaemons", {})
    normalized["capabilities"].setdefault("omit", [])
    normalized.setdefault("build", {})
    normalized["build"].setdefault("reduceFilesystem", False)

    normalized["capabilities"]["require"] = sorted(normalized["capabilities"]["require"])
    normalized["capabilities"]["omit"] = sorted(normalized["capabilities"]["omit"])
    return normalized


@dataclass(frozen=True)
class NormalizedManifest:
    """Immutable normalized manifest plus its canonical identity."""

    document: Mapping[str, Any]
    canonical_json: bytes
    sha256: str
    source: str

    @property
    def name(self) -> str:
        return self.document["metadata"]["name"]

    @property
    def required_capabilities(self) -> Tuple[str, ...]:
        return tuple(self.document["capabilities"]["require"])

    @property
    def omitted_capabilities(self) -> Tuple[str, ...]:
        return tuple(self.document["capabilities"]["omit"])


def load_manifest(path: str, schema_path: str = None) -> NormalizedManifest:
    source_path = Path(path)
    schema_file = Path(schema_path) if schema_path else DEFAULT_SCHEMA_PATH
    document = load_yaml(source_path, ManifestError)
    if not isinstance(document, dict):
        raise ManifestError("manifest root must be a mapping")

    try:
        with schema_file.open("r", encoding="utf-8") as stream:
            schema = json.load(stream)
    except (OSError, ValueError) as exc:
        raise ManifestError("unable to load manifest schema {}: {}".format(schema_file, exc)) from exc

    try:
        Draft4Validator.check_schema(schema)
    except Exception as exc:
        raise ManifestError("invalid manifest schema {}: {}".format(schema_file, exc)) from exc
    validator = Draft4Validator(schema)
    validation_errors = _format_errors(validator, document)
    if validation_errors:
        raise ManifestError(validation_errors)

    required = set(document["capabilities"]["require"])
    omitted = set(document["capabilities"].get("omit", []))
    overlap = sorted(required & omitted)
    if overlap:
        raise ManifestError("capabilities occur in both require and omit: {}".format(", ".join(overlap)))

    normalized = _normalize(document)
    canonical = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return NormalizedManifest(
        document=_freeze(normalized),
        canonical_json=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
        source=str(source_path),
    )
