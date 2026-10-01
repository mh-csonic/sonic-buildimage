import copy

import pytest

from sonic_config_version.errors import RepositoryError, ValidationError


def _add_vlan(adapter):
    adapter.running["VLAN"] = {"Vlan100": {"vlanid": "100"}}


def test_apply_dry_run_does_not_change_running_or_refs(sonicgit):
    manager, adapter = sonicgit
    baseline = manager.initialize()
    _add_vlan(adapter)
    vlan = manager.commit("vlan")
    before = copy.deepcopy(adapter.running)
    result = manager.apply(baseline["commit"], dry_run=True)
    assert result["dry_run"] is True
    assert adapter.running == before
    assert manager.status()["active_commit"] == vlan["commit"]


def test_apply_verifies_running_saves_startup_and_moves_refs(sonicgit):
    manager, adapter = sonicgit
    baseline = manager.initialize()
    _add_vlan(adapter)
    manager.commit("vlan")
    manager.apply(baseline["commit"])
    status = manager.status()
    assert "VLAN" not in adapter.running
    assert adapter.startup == adapter.running
    assert status["active_commit"] == baseline["commit"]
    assert status["startup_commit"] == baseline["commit"]
    assert status["running_matches_active"] is True


def test_apply_accepts_operator_label(sonicgit):
    manager, adapter = sonicgit
    baseline = manager.initialize(label="baseline")
    _add_vlan(adapter)
    manager.commit("vlan", label="vlan-100")

    result = manager.apply("baseline")

    assert result["target_commit"] == baseline["commit"]
    assert "VLAN" not in adapter.running


def test_default_rollback_selects_active_parent(sonicgit):
    manager, adapter = sonicgit
    baseline = manager.initialize()
    _add_vlan(adapter)
    manager.commit("vlan")
    result = manager.rollback()
    assert result["target_commit"] == baseline["commit"]
    assert "VLAN" not in adapter.running


def test_root_commit_cannot_be_default_rollback_target(sonicgit):
    manager, _ = sonicgit
    manager.initialize()
    with pytest.raises(RepositoryError):
        manager.rollback()


def test_partial_apply_failure_restores_and_persists_original(sonicgit):
    manager, adapter = sonicgit
    baseline = manager.initialize()
    _add_vlan(adapter)
    manager.commit("vlan")
    adapter.running["DEVICE_METADATA"]["localhost"]["hostname"] = "unsaved-live-state"
    original = copy.deepcopy(adapter.running)
    original_apply = adapter.apply_candidate

    def partial_failure(path):
        original_apply(path)
        raise RuntimeError("injected failure after mutation")

    adapter.apply_candidate = partial_failure
    with pytest.raises(RuntimeError):
        manager.apply(baseline["commit"])
    assert adapter.running == original
    assert adapter.startup == original
    assert any(event["action"] == "apply" and event["result"] == "failure" for event in manager.audit_events())


def test_candidate_platform_mismatch_is_rejected_before_checkpoint(sonicgit):
    manager, adapter = sonicgit
    baseline = manager.initialize()
    adapter.info["hwsku"] = "different"
    with pytest.raises(ValidationError):
        manager.apply(baseline["commit"])
    assert "create_checkpoint" not in adapter.calls


def test_mandatory_audit_failure_restores_configuration_and_refs(sonicgit):
    manager, adapter = sonicgit
    baseline = manager.initialize()
    _add_vlan(adapter)
    vlan = manager.commit("vlan")
    original = copy.deepcopy(adapter.running)
    real_append = manager.audit.append

    def failing_append(action, result, **details):
        if action == "apply" and result == "success":
            raise RuntimeError("audit unavailable")
        return real_append(action, result, **details)

    manager.audit.append = failing_append
    with pytest.raises(RuntimeError, match="audit unavailable"):
        manager.apply(baseline["commit"])
    assert adapter.running == original
    assert adapter.startup == original
    assert manager.status()["active_commit"] == vlan["commit"]


def test_checkpoint_cleanup_failure_does_not_undo_verified_apply(sonicgit):
    manager, adapter = sonicgit
    baseline = manager.initialize()
    _add_vlan(adapter)
    manager.commit("vlan")
    adapter.fail_on = "delete_checkpoint"
    result = manager.apply(baseline["commit"])
    assert result["checkpoint_deleted"] is False
    assert "VLAN" not in adapter.running
    assert manager.status()["active_commit"] == baseline["commit"]
