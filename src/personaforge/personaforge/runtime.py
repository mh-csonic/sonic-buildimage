import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .catalog import ReleaseCatalog, validate_manifest_against_catalog
from .errors import PersonaForgeContractError
from .manifest import NormalizedManifest


class RuntimeContractError(PersonaForgeContractError):
    """Runtime intent cannot be resolved or safely represented."""


@dataclass(frozen=True)
class RuntimeAction:
    table: str
    key: str
    field: str
    desired: Optional[str]
    previous: Optional[str]
    reason: str

    @property
    def changed(self) -> bool:
        return self.desired != self.previous


@dataclass(frozen=True)
class RuntimePlan:
    profile: str
    manifest_sha256: str
    catalog_sha256: str
    actions: Tuple[RuntimeAction, ...]
    allow_disruptive: bool = False
    persist_runtime: bool = False

    def as_dict(self) -> dict:
        return {
            "profile": self.profile,
            "manifestSha256": self.manifest_sha256,
            "catalogSha256": self.catalog_sha256,
            "policy": {
                "allowDisruptive": self.allow_disruptive,
                "persistRuntime": self.persist_runtime,
            },
            "actions": [asdict(action) for action in self.actions],
        }


def _desired_runtime_state(manifest: NormalizedManifest, catalog: ReleaseCatalog) -> Dict[Tuple[str, str, str], Tuple[str, str]]:
    validate_manifest_against_catalog(manifest, catalog)
    components = catalog.document["components"]
    desired = {}

    required = set()
    for capability in manifest.document["capabilities"]["require"]:
        required.update(catalog.document["capabilities"][capability])

    for capability in manifest.document["capabilities"]["omit"]:
        for component_name in catalog.document["capabilities"][capability]:
            component = components[component_name]
            if component_name in required or component["protected"]:
                continue
            if component["runtimeAdapter"] == "feature":
                desired[("FEATURE", component["featureName"], "state")] = (
                    "disabled", "omitted capability {}".format(capability)
                )
            elif component["runtimeAdapter"] == "frr-daemon":
                desired[("FRR_DAEMON", component["daemonName"], "admin_status")] = (
                    "disabled", "omitted capability {}".format(capability)
                )

    for feature, state in manifest.document["overrides"]["features"].items():
        if state != "default":
            desired[("FEATURE", feature, "state")] = (state, "explicit feature override")

    for daemon, state in manifest.document["overrides"]["frrDaemons"].items():
        desired[("FRR_DAEMON", daemon, "admin_status")] = (
            state, "explicit FRR daemon override"
        )
    return desired


def resolve_runtime_plan(
    manifest: NormalizedManifest,
    catalog: ReleaseCatalog,
    tables: Mapping[str, Mapping[str, Mapping[str, str]]],
) -> RuntimePlan:
    desired = _desired_runtime_state(manifest, catalog)
    actions = []
    for (table, key, field), (value, reason) in sorted(desired.items()):
        entry = (tables.get(table) or {}).get(key)
        # A build-pruned FEATURE has no runtime owner and needs no ConfigDB row.
        if table == "FEATURE" and entry is None:
            continue
        previous = entry.get(field) if entry else None
        actions.append(RuntimeAction(table, key, field, value, previous, reason))
    return RuntimePlan(
        manifest.name,
        manifest.sha256,
        catalog.sha256,
        tuple(actions),
        bool(manifest.document["policy"]["allowDisruptive"]),
        bool(manifest.document["policy"]["persistRuntime"]),
    )


def inverse_actions(metadata: Mapping[str, object]) -> Tuple[RuntimeAction, ...]:
    actions = []
    for item in metadata.get("actions", []):
        actions.append(RuntimeAction(
            item["table"], item["key"], item["field"], item.get("previous"),
            item.get("desired"), "deactivate {}".format(metadata.get("profile", "persona")),
        ))
    return tuple(reversed(actions))


def create_active_metadata(plan: RuntimePlan, persisted: bool, status: str = "active") -> dict:
    result = plan.as_dict()
    result.update({
        "schemaVersion": 1,
        "status": status,
        "persisted": bool(persisted),
        "updatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    })
    return result


def calculate_drift(
    metadata: Mapping[str, object],
    tables: Mapping[str, Mapping[str, Mapping[str, str]]],
) -> list:
    drift = []
    for action in metadata.get("actions", []):
        entry = (tables.get(action["table"]) or {}).get(action["key"]) or {}
        actual = entry.get(action["field"])
        if actual != action.get("desired"):
            drift.append({
                "table": action["table"],
                "key": action["key"],
                "field": action["field"],
                "desired": action.get("desired"),
                "actual": actual,
            })
    return drift


def atomic_write_json(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".{}-".format(path.name), dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(str(path.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def read_metadata(paths: Sequence[Path]) -> Tuple[Optional[dict], Optional[Path]]:
    for path in paths:
        try:
            with path.open("r", encoding="utf-8") as stream:
                document = json.load(stream)
            if document.get("schemaVersion") != 1:
                raise RuntimeContractError("unsupported active metadata schema in {}".format(path))
            return document, path
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            raise RuntimeContractError("unable to read active metadata {}: {}".format(path, exc)) from exc
    return None, None


def resolve_profile_path(value: str, search_dirs: Iterable[Path]) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or candidate.parent != Path(".") or candidate.suffix:
        if not candidate.is_file():
            raise RuntimeContractError("persona profile does not exist: {}".format(value))
        return candidate
    if not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", value):
        raise RuntimeContractError("invalid persona profile name: {}".format(value))
    for directory in search_dirs:
        path = directory / "{}.yaml".format(value)
        if path.is_file():
            return path
    raise RuntimeContractError("unknown persona profile: {}".format(value))
