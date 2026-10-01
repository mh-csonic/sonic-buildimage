import click

from sonic_config_version.cli.common import manager, require_root, run


@click.group("sonic-git")
def sonic_git():
    """Manage local Git-backed configuration versions."""


@sonic_git.command("init")
@click.option("--label", help="Optional lowercase label for the baseline commit.")
def initialize(label):
    """Create the repository and capture the running configuration baseline."""
    require_root()
    run(lambda: manager().initialize(label=label))


@sonic_git.command("commit")
@click.option("--message", "message", required=True, help="Description of the running configuration change.")
@click.option("--allow-empty", is_flag=True, help="Allow a semantic no-op snapshot commit.")
@click.option("--label", help="Optional lowercase label for the new commit.")
def commit(message, allow_empty, label):
    """Commit the current running CONFIG_DB."""
    require_root()
    run(lambda: manager().commit(message, allow_empty=allow_empty, label=label))


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


@sonic_git.group("label")
def label_group():
    """Create or delete operator-friendly configuration labels."""


@label_group.command("create")
@click.argument("name")
@click.argument("revision", required=False, default="refs/sonic/active")
def create_label(name, revision):
    """Attach NAME to REVISION, or to the active commit when omitted."""
    require_root()
    run(lambda: manager().create_label(name, revision))


@label_group.command("delete")
@click.argument("name")
def delete_label(name):
    """Delete NAME without deleting its configuration commit."""
    require_root()
    run(lambda: manager().delete_label(name))
