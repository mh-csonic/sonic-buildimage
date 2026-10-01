def rollback_revision(manager, revision=None, dry_run=False):
    return manager.rollback(revision, dry_run=dry_run)
