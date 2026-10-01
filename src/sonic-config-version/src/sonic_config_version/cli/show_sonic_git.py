import click

from sonic_config_version.cli.common import manager, require_root, run
from sonic_config_version.cli.formatters import (
    format_audit,
    format_capability,
    format_diff,
    format_drift,
    format_history,
    format_inspect,
    format_labels,
    format_status,
)


@click.group("sonic-git")
def sonic_git():
    """Show local Git-backed configuration information."""
    require_root("accessing SonicGit's private state")


@sonic_git.command("status")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def status(json_output):
    """Show active, startup, and observed configuration state."""
    run(lambda: manager().status(), renderer=format_status, json_output=json_output)


@sonic_git.command("history")
@click.option("--limit", type=click.IntRange(1, 1000), default=20, show_default=True)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def history(limit, json_output):
    """Show local configuration commit history."""
    run(lambda: manager().history(limit), renderer=format_history, json_output=json_output)


@sonic_git.command("diff")
@click.argument("from_revision")
@click.argument("to_revision")
@click.option("--format", "output_format", type=click.Choice(["semantic", "git"]), default="semantic")
@click.option("--json", "json_output", is_flag=True, help="Emit semantic changes as JSON.")
def diff(from_revision, to_revision, output_format, json_output):
    """Compare two local configuration commits."""
    if output_format == "git":
        if json_output:
            raise click.UsageError("--json cannot be combined with --format git")
        run(lambda: manager().diff(from_revision, to_revision, output_format="git"))
        return
    if json_output:
        run(lambda: manager().diff_report(from_revision, to_revision)["changes"])
        return
    run(lambda: manager().diff_report(from_revision, to_revision), renderer=format_diff)


@sonic_git.command("drift")
@click.option("--verbose", is_flag=True, help="Include every semantic change.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def drift(verbose, json_output):
    """Compare running CONFIG_DB with the active commit."""
    run(lambda: manager().drift(verbose=verbose), renderer=format_drift, json_output=json_output)


@sonic_git.command("audit")
@click.option("--limit", type=click.IntRange(1, 1000), default=20, show_default=True)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def audit(limit, json_output):
    """Show recent local SonicGit audit records."""
    run(lambda: manager().audit_events(limit), renderer=format_audit, json_output=json_output)


@sonic_git.command("capability")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def capability(json_output):
    """Show platform, Git, repository-policy, and native command capabilities."""
    run(lambda: manager().capability(), renderer=format_capability, json_output=json_output)


@sonic_git.command("labels")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def labels(json_output):
    """List operator-friendly labels and their immutable commits."""
    run(lambda: manager().labels(), renderer=format_labels, json_output=json_output)


@sonic_git.command("inspect")
@click.argument("revision")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def inspect(revision, json_output):
    """Show metadata for a label, SHA, or other local revision."""
    run(lambda: manager().inspect_revision(revision), renderer=format_inspect, json_output=json_output)
