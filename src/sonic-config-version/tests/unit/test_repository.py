import json

import pytest

from sonic_config_version.constants import ACTIVE_REF, STARTUP_REF
from sonic_config_version.errors import NoChangeError, RepositoryError, ValidationError


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


def test_history_reports_operator_from_each_commit(monkeypatch, sonicgit):
    manager, adapter = sonicgit
    monkeypatch.setenv("SUDO_USER", "baseline-operator")
    baseline = manager.initialize()
    monkeypatch.setenv("SUDO_USER", "vlan-operator")
    adapter.running["VLAN"] = {"Vlan100": {"vlanid": "100"}}
    vlan = manager.commit("vlan")

    history = {entry["commit"]: entry for entry in manager.history()}

    assert history[baseline["commit"]]["author"] == "SonicGit"
    assert history[baseline["commit"]]["operator"] == "baseline-operator"
    assert history[vlan["commit"]]["author"] == "SonicGit"
    assert history[vlan["commit"]]["operator"] == "vlan-operator"


def test_audit_reports_operator_for_success_and_failure(monkeypatch, sonicgit):
    manager, _ = sonicgit
    monkeypatch.setenv("SUDO_USER", "successful-operator")
    manager.initialize()
    monkeypatch.setenv("SUDO_USER", "failing-operator")
    with pytest.raises(NoChangeError):
        manager.commit("no change")

    events = manager.audit_events()

    assert next(event for event in events if event["action"] == "init")["operator"] == "successful-operator"
    failure = next(event for event in events if event["action"] == "commit" and event["result"] == "failure")
    assert failure["operator"] == "failing-operator"


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


def test_labels_resolve_to_commits_and_appear_in_history(sonicgit):
    manager, adapter = sonicgit
    baseline = manager.initialize(label="baseline")
    adapter.running["VLAN"] = {"Vlan100": {"vlanid": "100"}}
    vlan = manager.commit("vlan", label="vlan-100")

    assert manager.repository.resolve_revision("baseline") == baseline["commit"]
    assert manager.repository.resolve_revision("vlan-100") == vlan["commit"]
    history = {entry["commit"]: entry for entry in manager.history()}
    assert history[baseline["commit"]]["labels"] == ["baseline"]
    assert history[vlan["commit"]]["labels"] == ["vlan-100"]


def test_label_names_are_unique_immutable_and_audited(sonicgit):
    manager, _ = sonicgit
    baseline = manager.initialize()
    created = manager.create_label("known-good", baseline["commit"])
    assert created == {"label": "known-good", "commit": baseline["commit"]}

    with pytest.raises(RepositoryError, match="already exists"):
        manager.create_label("known-good", baseline["commit"])

    with pytest.raises(RepositoryError, match="already has label 'known-good'"):
        manager.create_label("baseline-copy", baseline["commit"])

    deleted = manager.delete_label("known-good")
    assert deleted["deleted"] is True
    with pytest.raises(RepositoryError):
        manager.repository.resolve_revision("known-good")

    replacement = manager.create_label("baseline-copy", baseline["commit"])
    assert replacement == {"label": "baseline-copy", "commit": baseline["commit"]}

    events = manager.audit_events()
    assert any(event["action"] == "label-create" and event["result"] == "success" for event in events)
    assert any(event["action"] == "label-create" and event["result"] == "failure" for event in events)
    assert any(event["action"] == "label-delete" and event["result"] == "success" for event in events)


def test_label_name_cannot_be_reassigned_to_another_commit(sonicgit):
    manager, adapter = sonicgit
    baseline = manager.initialize(label="known-good")
    adapter.running["VLAN"] = {"Vlan100": {"vlanid": "100"}}
    candidate = manager.commit("add VLAN 100")

    with pytest.raises(RepositoryError, match="already exists at {}".format(baseline["commit"])):
        manager.create_label("known-good", candidate["commit"])


@pytest.mark.parametrize("label", ["Known-Good", "HEAD", "active", "deadbeef", "contains space"])
def test_unsafe_or_ambiguous_labels_are_rejected(sonicgit, label):
    manager, _ = sonicgit
    manager.initialize()
    with pytest.raises(ValidationError):
        manager.create_label(label)
