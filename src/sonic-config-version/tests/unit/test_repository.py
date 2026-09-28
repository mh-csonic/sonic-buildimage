import json

import pytest

from sonic_config_version.constants import ACTIVE_REF, STARTUP_REF
from sonic_config_version.errors import NoChangeError, RepositoryError


def test_init_creates_baseline_and_refs(sonicgit):
    manager, _ = sonicgit
    result = manager.initialize()
    assert len(result["commit"]) == 40
    assert manager.repository.resolve_optional_ref(ACTIVE_REF) == result["commit"]
    assert manager.repository.resolve_optional_ref(STARTUP_REF) == result["commit"]
    snapshot, metadata = manager.repository.load_snapshot(result["commit"])
    assert metadata["configuration_sha256"] == result["configuration_sha256"]
    assert json.loads(snapshot)["DEVICE_METADATA"]["localhost"]["hostname"] == "sonic"


def test_duplicate_init_and_noop_commit_are_rejected(sonicgit):
    manager, _ = sonicgit
    manager.initialize()
    with pytest.raises(RepositoryError):
        manager.initialize()
    with pytest.raises(NoChangeError):
        manager.commit("no change")


def test_allow_empty_records_snapshot(sonicgit):
    manager, _ = sonicgit
    first = manager.initialize()
    second = manager.commit("intentional marker", allow_empty=True)
    assert second["commit"] != first["commit"]
    assert len(manager.history()) == 2


def test_history_retains_diverged_commits_and_parent_tracks_active(sonicgit):
    manager, adapter = sonicgit
    baseline = manager.initialize()
    adapter.running["VLAN"] = {"Vlan100": {"vlanid": "100"}}
    vlan = manager.commit("vlan")
    manager.apply(baseline["commit"])
    adapter.running["LOOPBACK_INTERFACE"] = {"Loopback0|10.0.0.1/32": {}}
    loopback = manager.commit("loopback")
    assert len(manager.history()) == 3
    _, metadata = manager.repository.load_snapshot(loopback["commit"])
    assert metadata["parent"] == baseline["commit"]
    assert manager.repository.parent_of_active() == baseline["commit"]
    assert vlan["commit"] in {entry["commit"] for entry in manager.history()}


def test_remote_blocks_modifying_operation(sonicgit):
    manager, adapter = sonicgit
    manager.initialize()
    manager.repository.git.run("remote", "add", "origin", "https://example.invalid/repo")
    adapter.running["VLAN"] = {"Vlan100": {}}
    with pytest.raises(RepositoryError):
        manager.commit("must fail")
