# SonicGit local configuration versioning

SonicGit is a synchronous, device-local configuration history for single-ASIC
SONiC switches. It snapshots running Redis `CONFIG_DB` into a persistent local
Git repository and uses existing SONiC commands to validate, apply, save, and
restore selected snapshots.

It does not run a daemon, contact a remote Git server, monitor switch health,
or automatically commit when `config save` is run. A Git checkout never applies
configuration.

## Commands

```text
sudo config sonic-git init
sudo config sonic-git commit --message <message> [--allow-empty]
sudo config sonic-git apply <revision> [--dry-run]
sudo config sonic-git rollback [<revision>] [--dry-run]

show sonic-git status
show sonic-git history [--limit <count>]
show sonic-git diff <from> <to> [--format semantic|git]
show sonic-git drift [--verbose]
show sonic-git audit [--limit <count>]
show sonic-git capability
```

The default state root is `/var/lib/sonic/config-version`. The repository is
local-only. Adding any Git remote blocks init, commit, apply, and rollback.

## Safety model

An apply or rollback pins a revision to a full commit SHA, verifies its files,
checksum, metadata, platform, HWSKU, SONiC release, and ASIC count, then:

1. Exports a stable pre-operation running configuration.
2. Creates a native SONiC checkpoint and verifies its hash.
3. Runs native `config replace --dry-run` and proves running state did not move.
4. Runs native `config replace` and verifies the running hash.
5. Runs `config save -y` and verifies `/etc/sonic/config_db.json`.
6. Moves `refs/sonic/active` and `refs/sonic/startup` only after verification.

If mutation, verification, or persistence fails, SonicGit invokes native
checkpoint rollback, verifies the original running hash, saves it, and verifies
the restored startup hash. A failed safety restoration is reported as critical
and its checkpoint metadata is preserved for operator investigation.

The MVP is single-ASIC only. Operators must not run another configuration-
changing command concurrently with `sonic-git apply` or `sonic-git rollback`.

See `TESTING.md` for off-box, image, VS, and Broadcom acceptance steps.
