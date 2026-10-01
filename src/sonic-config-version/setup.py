from setuptools import find_packages, setup


setup(
    name="sonic-config-version",
    version="1.0.0",
    description="Local Git-backed SONiC configuration versioning",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=["click>=7"],
)
