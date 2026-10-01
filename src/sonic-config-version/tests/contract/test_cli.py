import json

from click.testing import CliRunner

from sonic_config_version.cli.config_sonic_git import sonic_git as config_group
from sonic_config_version.cli.show_sonic_git import sonic_git as show_group


def test_config_command_contract():
    result = CliRunner().invoke(config_group, ["--help"])
    assert result.exit_code == 0
    assert set(config_group.commands) == {"init", "commit", "apply", "rollback", "label"}
    assert set(config_group.commands["label"].commands) == {"create", "delete"}


def test_show_command_contract():
    result = CliRunner().invoke(show_group, ["--help"])
    assert result.exit_code == 0
    assert set(show_group.commands) == {
        "status",
        "history",
        "diff",
        "drift",
        "audit",
        "capability",
        "labels",
        "inspect",
    }


def test_show_commands_reject_non_root_with_clear_error(monkeypatch):
    monkeypatch.setattr("sonic_config_version.cli.common.os.geteuid", lambda: 1000)

    result = CliRunner().invoke(show_group, ["status"])

    assert result.exit_code == 2
    assert "root privileges are required for accessing SonicGit's private state" in result.output
    assert "initialized" not in result.output


def _bind_manager(monkeypatch, instance):
    monkeypatch.setattr("sonic_config_version.cli.common.os.geteuid", lambda: 0)
    monkeypatch.setattr("sonic_config_version.cli.show_sonic_git.manager", lambda: instance)
    monkeypatch.setattr("sonic_config_version.cli.config_sonic_git.manager", lambda: instance)


def test_show_status_history_and_diff_use_human_readable_output(monkeypatch, sonicgit):
    manager, adapter = sonicgit
    _bind_manager(monkeypatch, manager)
    baseline = manager.initialize(label="baseline")
    adapter.running["PORT"] = {"Ethernet64": {"admin_status": "up"}}
    candidate = manager.commit("enable Ethernet64", label="port-up")
    runner = CliRunner()

    status = runner.invoke(show_group, ["status"])
    history = runner.invoke(show_group, ["history"])
    diff = runner.invoke(show_group, ["diff", "baseline", "port-up"])

    assert status.exit_code == 0
    assert "Repository status" in status.output
    assert "Running version" in status.output
    assert "port-up ({})".format(candidate["commit"][:8]) in status.output
    assert history.exit_code == 0
    assert "STATE" not in history.output
    assert history.output.splitlines()[0].startswith("LABEL")
    assert "baseline" in history.output
    assert "port-up" in history.output
    assert diff.exit_code == 0
    assert "From: baseline ({})".format(baseline["commit"][:8]) in diff.output
    assert "To:   port-up ({})".format(candidate["commit"][:8]) in diff.output
    assert "OPERATION" in diff.output
    assert "PORT" in diff.output
    assert "Ethernet64" in diff.output
    assert "admin_status" in diff.output


def test_show_drift_summarizes_entries_and_verbose_changes(monkeypatch, sonicgit):
    manager, adapter = sonicgit
    _bind_manager(monkeypatch, manager)
    manager.initialize(label="baseline")
    adapter.running["VLAN"] = {"Vlan100": {"vlanid": "100"}}

    result = CliRunner().invoke(show_group, ["drift", "--verbose"])

    assert result.exit_code == 0
    assert "Drift" in result.output
    assert "Detected" in result.output
    assert "Tables changed : 1" in result.output
    assert "Entries added  : 1" in result.output
    assert "ADD" in result.output
    assert "VLAN" in result.output
    assert "Vlan100" in result.output


def test_show_json_retains_machine_readable_output(monkeypatch, sonicgit):
    manager, _ = sonicgit
    _bind_manager(monkeypatch, manager)
    manager.initialize(label="baseline")

    result = CliRunner().invoke(show_group, ["history", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload[0]["labels"] == ["baseline"]
    assert "state" not in payload[0]


def test_label_commands_create_list_inspect_and_delete(monkeypatch, sonicgit):
    manager, _ = sonicgit
    _bind_manager(monkeypatch, manager)
    manager.initialize()
    runner = CliRunner()

    created = runner.invoke(config_group, ["label", "create", "known-good"])
    labels = runner.invoke(show_group, ["labels"])
    inspected = runner.invoke(show_group, ["inspect", "known-good"])
    deleted = runner.invoke(config_group, ["label", "delete", "known-good"])

    assert created.exit_code == 0
    assert json.loads(created.output)["label"] == "known-good"
    assert labels.exit_code == 0
    assert "known-good" in labels.output
    assert "STATE" not in labels.output
    assert labels.output.splitlines()[0].startswith("LABEL")
    assert inspected.exit_code == 0
    assert "Label" in inspected.output
    assert "known-good" in inspected.output
    assert deleted.exit_code == 0
    assert json.loads(deleted.output)["deleted"] is True


def test_second_label_for_active_commit_is_rejected(monkeypatch, sonicgit):
    manager, _ = sonicgit
    _bind_manager(monkeypatch, manager)
    manager.initialize(label="baseline")

    result = CliRunner().invoke(config_group, ["label", "create", "known-good"])

    assert result.exit_code != 0
    assert "already has label 'baseline'" in result.output


def test_audit_human_output_does_not_embed_json_details(monkeypatch, sonicgit):
    manager, _ = sonicgit
    _bind_manager(monkeypatch, manager)
    manager.initialize(label="baseline")

    result = CliRunner().invoke(show_group, ["audit", "--limit", "1"])

    assert result.exit_code == 0
    assert "OP ID" in result.output
    assert "label=baseline" in result.output
    assert "{" not in result.output
