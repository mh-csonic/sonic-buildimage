import click

from sonic_config_version.cli.common import manager, require_root, run


@click.group("sonic-git")
def sonic_git():
    """Manage local Git-backed configuration versions."""


@sonic_git.command("init")
def initialize():
    """Create the repository and capture the running configuration baseline."""
    require_root()
    run(lambda: manager().initialize())


@sonic_git.command("commit")
@click.option("--message", "message", required=True, help="Description of the running configuration change.")
@click.option("--allow-empty", is_flag=True, help="Allow a semantic no-op snapshot commit.")
def commit(message, allow_empty):
    """Commit the current running CONFIG_DB."""
    require_root()
    run(lambda: manager().commit(message, allow_empty=allow_empty))


@sonic_git.command("apply")
@click.argument("revision")
@click.option("--dry-run", is_flag=True, help="Run native validation without changing configuration.")
def apply(revision, dry_run):
    """Apply a pinned local configuration revision."""
    require_root()
    run(lambda: manager().apply(revision, dry_run=dry_run))


@sonic_git.command("rollback")
@click.argument("revision", required=False)
@click.option("--dry-run", is_flag=True, help="Run native validation without changing configuration.")
def rollback(revision, dry_run):
    """Restore a revision, or the active commit's first parent."""
    require_root()
    run(lambda: manager().rollback(revision, dry_run=dry_run))
