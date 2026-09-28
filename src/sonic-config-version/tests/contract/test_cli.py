from click.testing import CliRunner

from sonic_config_version.cli.config_sonic_git import sonic_git as config_group
from sonic_config_version.cli.show_sonic_git import sonic_git as show_group


def test_config_command_contract():
    result = CliRunner().invoke(config_group, ["--help"])
    assert result.exit_code == 0
    assert set(config_group.commands) == {"init", "commit", "apply", "rollback"}


def test_show_command_contract():
    result = CliRunner().invoke(show_group, ["--help"])
    assert result.exit_code == 0
    assert set(show_group.commands) == {"status", "history", "diff", "drift", "audit", "capability"}
