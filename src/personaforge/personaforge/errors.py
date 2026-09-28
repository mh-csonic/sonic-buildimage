class PersonaForgeContractError(ValueError):
    """Base class for rejected PersonaForge contract data."""


class ManifestError(PersonaForgeContractError):
    """A persona manifest is unsafe, malformed, or semantically invalid."""


class CatalogError(PersonaForgeContractError):
    """A release catalog is malformed or internally inconsistent."""
