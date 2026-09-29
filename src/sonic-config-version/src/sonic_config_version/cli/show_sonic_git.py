import click

from sonic_config_version.cli.common import manager, require_root, run


@click.group("sonic-git")
def sonic_git():
    """Show local Git-backed configuration information."""
    require_root("accessing SonicGit's private state")


@sonic_git.command("status")
def status():
    """Show active, startup, and observed configuration state."""
    run(lambda: manager().status())


@sonic_git.command("history")
@click.option("--limit", type=click.IntRange(1, 1000), default=20, show_default=True)
def history(limit):
    """Show local configuration commit history."""
    run(lambda: manager().history(limit))


@sonic_git.command("diff")
@click.argument("from_revision")
@click.argument("to_revision")
@click.option("--format", "output_format", type=click.Choice(["semantic", "git"]), default="semantic")
def diff(from_revision, to_revision, output_format):
    """Compare two local configuration commits."""
    run(lambda: manager().diff(from_revision, to_revision, output_format=output_format))


@sonic_git.command("drift")
@click.option("--verbose", is_flag=True, help="Include every semantic change.")
def drift(verbose):
    """Compare running CONFIG_DB with the active commit."""
    run(lambda: manager().drift(verbose=verbose))


@sonic_git.command("audit")
@click.option("--limit", type=click.IntRange(1, 1000), default=20, show_default=True)
def audit(limit):
    """Show recent local SonicGit audit records."""
    run(lambda: manager().audit_events(limit))


@sonic_git.command("capability")
def capability():
    """Show platform, Git, repository-policy, and native command capabilities."""
    run(lambda: manager().capability())
