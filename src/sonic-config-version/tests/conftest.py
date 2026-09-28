import os

import pytest

from sonic_config_version.adapters.fake import FakeSonicAdapter
from sonic_config_version.manager import SonicGitManager


@pytest.fixture
def initial_config():
    return {"DEVICE_METADATA": {"localhost": {"hostname": "sonic"}}}


@pytest.fixture
def sonicgit(tmp_path, initial_config):
    adapter = FakeSonicAdapter(initial_config)
    manager = SonicGitManager(
        str(tmp_path / "state"),
        adapter=adapter,
        reload_lock_path=str(tmp_path / "reload.lock"),
        required_uid=os.geteuid(),
    )
    return manager, adapter
