"""PersonaForge contract loaders and immutable normalized models."""

from .catalog import ReleaseCatalog, load_catalog, validate_manifest_against_catalog
from .build import BuildContract, BuildContractError, resolve_build_contract, write_build_outputs
from .errors import CatalogError, ManifestError, PersonaForgeContractError
from .manifest import NormalizedManifest, load_manifest
from .runtime import (
    RuntimeAction,
    RuntimeContractError,
    RuntimePlan,
    atomic_write_json,
    calculate_drift,
    create_active_metadata,
    inverse_actions,
    read_metadata,
    resolve_profile_path,
    resolve_runtime_plan,
)

__all__ = [
    "CatalogError",
    "BuildContract",
    "BuildContractError",
    "ManifestError",
    "NormalizedManifest",
    "PersonaForgeContractError",
    "ReleaseCatalog",
    "RuntimeAction",
    "RuntimeContractError",
    "RuntimePlan",
    "atomic_write_json",
    "calculate_drift",
    "create_active_metadata",
    "inverse_actions",
    "load_catalog",
    "load_manifest",
    "resolve_build_contract",
    "read_metadata",
    "resolve_profile_path",
    "resolve_runtime_plan",
    "validate_manifest_against_catalog",
    "write_build_outputs",
]
