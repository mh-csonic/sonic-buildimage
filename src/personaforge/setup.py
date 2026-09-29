from pathlib import Path

from setuptools import find_packages, setup


ROOT = Path(__file__).resolve().parent
PROFILE_ROOT = ROOT.parents[1] / "personaforge" / "profiles"


setup(
    name="sonic-personaforge",
    version="0.1.0",
    description="PersonaForge manifest and release-catalog contracts",
    packages=find_packages(),
    data_files=[
        ("share/personaforge/schema", [str(path) for path in sorted((ROOT / "schema").glob("*.json"))]),
        ("share/personaforge/catalogs", [str(path) for path in sorted((ROOT / "catalogs").glob("*.yaml"))]),
        ("share/personaforge/profiles", [str(path) for path in sorted(PROFILE_ROOT.glob("*.yaml"))]),
    ],
    install_requires=["PyYAML>=5.4", "jsonschema>=2.6"],
    python_requires=">=3.8",
)
