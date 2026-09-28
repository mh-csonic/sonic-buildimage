# SonicGit build and test guide

## 1. Off-box checks

From the `sonic-buildimage` root, install `pytest` in your normal development
environment or build container, then run:

```bash
PYTHONPATH=src/sonic-config-version/src \
pytest -q src/sonic-config-version/tests

PYTHONPATH=src/sonic-config-version/src \
python3 -m compileall -q src/sonic-config-version/src

git diff --check
```

The unit suite uses a fake SONiC adapter and a temporary real Git repository. It
does not read or change the build host's SONiC configuration.

## 2. Build the Broadcom image

Use the normal build setup for this checkout:

```bash
make init
make configure PLATFORM=broadcom
make target/sonic-broadcom.bin
```

The resulting image is:

```text
target/sonic-broadcom.bin
```

The shared Debian image template installs `sonic-config-version`, whose package
dependency installs host `/usr/bin/git`. This applies to both VS and Broadcom
images built through that template.

To build only the package while iterating, use the target emitted by the build
dependency graph (normally):

```bash
make target/debs/bookworm/sonic-config-version_1.0.0-1_all.deb
```

If this checkout is configured for a different Debian release, use the matching
directory below `target/debs/`.

## 3. Capability smoke test on the switch

Boot the newly built image on a single-ASIC switch, then run:

```bash
show version
dpkg -l sonic-config-version git
command -v git
show sonic-git capability
sudo ip netns list
```

Expected results:

- Existing `show version` still works.
- `sonic-config-version` and `git` are installed.
- Git resolves to `/usr/bin/git`.
- Capability reports ASIC count `1`, the expected platform/HWSKU/release, zero
  remotes, and available export/replace/checkpoint/rollback/save commands.
- The switch is not multi-ASIC. An empty namespace list is normal for the
  single-ASIC switch previously described.

Do not continue to apply/rollback if the capability result is missing a native
command or reports more than one ASIC.

## 4. Baseline and commit workflow

```bash
sudo config sonic-git init
show sonic-git status
show sonic-git history
sudo /usr/bin/git -C /var/lib/sonic/config-version/repository remote
```

The remote command must print nothing. Save the full baseline commit SHA shown
by history as `A`.

Make a small, lab-safe VLAN change using the commands appropriate for the test
topology. For example:

```bash
sudo config vlan add 100
sudo config sonic-git commit --message "add VLAN 100"
show sonic-git history
show sonic-git diff A refs/sonic/active --format semantic
show sonic-git drift --verbose
```

Save the VLAN commit SHA as `B`. The diff should show the VLAN additions and
drift should report no changes immediately after the commit.

To prove commits use running Redis rather than startup JSON, do not run
`config save` before this commit. `refs/sonic/startup` should remain at the last
snapshot whose hash matches `/etc/sonic/config_db.json`.

## 5. Dry-run, apply, and rollback

With commit `B` active:

```bash
sudo config sonic-git apply A --dry-run
show sonic-git status
show vlan brief
```

The dry-run must leave the running hash, active ref, and VLAN unchanged.

Apply the baseline explicitly:

```bash
sudo config sonic-git apply A
show sonic-git status
show vlan brief
```

Running and startup hashes must match `A`, and VLAN 100 should be absent.

Apply the VLAN version and then use default rollback:

```bash
sudo config sonic-git apply B
show vlan brief
sudo config sonic-git rollback
show sonic-git status
show vlan brief
```

Default rollback selects the first parent of the active commit. An explicit
rollback can select any valid local commit:

```bash
sudo config sonic-git rollback A
```

## 6. Drift and `config save`

Make a lab-safe running change without committing it:

```bash
sudo config vlan add 200
show sonic-git drift --verbose
```

Drift should report the semantic change. SonicGit never reconciles it
automatically. Either remove the change or adopt it explicitly with:

```bash
sudo config sonic-git commit --message "add VLAN 200"
```

`config save` does not trigger a SonicGit commit. Verify this by comparing
history before and after:

```bash
show sonic-git history
sudo config save -y
show sonic-git history
```

## 7. Audit, persistence, and failure testing

```bash
show sonic-git audit --limit 50
sudo find /var/lib/sonic/config-version -maxdepth 3 -type f -ls
```

Audit should contain init/commit/apply/rollback outcomes without configuration
secrets. State files must be root-owned and unavailable to group/other users.

After a successful rollback, reboot the lab switch and verify:

```bash
sudo reboot
# After the switch returns:
show sonic-git status
show vlan brief
```

Running and startup state should still match the selected commit.

Test failed-apply restoration on VS before hardware. Inject a controlled native
replace failure in a disposable lab image, then confirm the command fails, the
pre-operation running hash is restored, startup is saved to the same hash, and
the failure appears in `show sonic-git audit`. Do not inject failures on a
production or remotely inaccessible switch.

## 8. Final acceptance

Repeat the baseline (`A`), VLAN (`B`), and optional lab BGP (`C`) sequence first
on VS and then on the selected Broadcom TD3/TD4 switch. For every apply and
rollback, record:

- selected commit SHA;
- running and startup SHA-256 from status;
- semantic diff;
- native checkpoint evidence and SonicGit audit result;
- relevant VLAN/BGP operational state;
- post-reboot state for the final rollback.

The MVP is accepted only when this passes with zero Git remotes and no internet
dependency at runtime.
