# PersonaForge Implementation and Manual Test Guide

## 1. Scope

This document describes the PersonaForge implementation in the SONiC source tree, the demo personas shipped with it, and a manual test flow for understanding build-time reduction, runtime activation, and persistence across container and node restarts.

Related design documents:

- [PersonaForge Requirements Specification](docs/PersonaForge-Requirements.md)
- [PersonaForge High-Level Design](docs/PersonaForge-HLD.md)

The implementation is pinned to the SONiC `202605` release contract but does not restrict the selected build platform or ASIC count. The current source commit and selected platform remain part of the deterministic build identity so outputs from different revisions or targets cannot collide. Each hardware target still requires its normal SONiC build support and target-specific functional qualification. Rollback orchestration is intentionally deferred. The current `deactivate` command restores the values captured when a persona was applied, but it is not a global transactional rollback facility.

## 2. What is implemented

### 2.1 Persona contract and catalog

- A strict `v1alpha1` JSON schema validates persona YAML files.
- The `202605` release catalog maps capabilities to SONiC components, build variables, runtime adapters, dependency-probe names, verification methods, and activation methods.
- Persona and catalog inputs are normalized and hashed, making the build identity deterministic.
- Unknown fields, invalid states, duplicate YAML keys, unknown capabilities, and attempts to disable required components are rejected.
- Profiles and the release catalog are packaged in the `sonic-personaforge` wheel for runtime CLI use.

### 2.2 Build integration

- `PERSONAFORGE_PROFILE=<name>` selects a profile during a SONiC image build.
- `rules/personaforge.mk` resolves the profile before normal image rules consume the generated settings.
- Generated artifacts include the normalized manifest, normalized catalog, build plan, identity input, build key, and Make settings.
- Existing conflicting command-line, environment, or `rules/config.user` settings fail the build instead of silently overriding persona intent.
- Supported optional components are controlled through existing SONiC build variables such as `INCLUDE_TEAMD`, `INCLUDE_LLDP`, `INCLUDE_SNMP`, `INCLUDE_SYSTEM_GNMI`, and `INCLUDE_SYSTEM_TELEMETRY`. gNMI and telemetry use separate baseline controls and are resolved independently.
- Every catalog-controlled setting and `BUILD_REDUCE_IMAGE_SIZE` is passed explicitly from `Makefile.work` to the `slave.mk` invocation. This is required for values set to `n`, because several baseline defaults are `y` and the legacy `SONIC_INCLUDE_*` compatibility mappings only promote `y` values.
- `BUILD_REDUCE_IMAGE_SIZE` is controlled by each persona's `build.reduceFilesystem` value.

Build persistence is inherent in the resulting image: omitted packages and generated image contents remain the same after a Docker-container restart or node reboot because they are part of the built image. It does not require `config save`.

### 2.3 FRR daemon control

The ConfigDB table `FRR_DAEMON` controls the optional allowlisted daemons:

- `bfdd`
- `ospfd`
- `pimd`
- `pathd`

The FRR supervisor and critical-process templates omit disabled daemons. `frrcfgd` filters disabled clients, and classic `bgpcfgd` avoids starting or managing BFD when `bfdd` is disabled. Core routing processes such as `zebra`, `bgpd`, and `staticd` remain protected.

Changing an FRR daemon requires an explicit `--allow-disruptive` authorization because the current activation mechanism restarts `bgp.service`.

### 2.4 Native SONiC CLI

The following commands are implemented:

```text
show personaforge plan <profile> [--json]
show personaforge status [--detail] [--json]
show personaforge drift [--json]

config personaforge apply <profile> --allow-disruptive [--persist] [-y]
config personaforge persist [-y]
config personaforge deactivate --allow-disruptive [--persist] [-y]
```

Runtime behavior includes:

- read-only planning before mutation;
- validated ConfigDB writes;
- explicit disruptive-operation authorization;
- BGP service restart and active-state verification for FRR changes;
- ConfigDB value verification after apply;
- idempotent reapply of the same persona;
- rejection of a different persona until the active one is deactivated;
- live drift reporting;
- live metadata in `/run/personaforge/active.json`;
- durable metadata in `/var/lib/personaforge/active.json` after successful persistence.

### 2.5 Runtime persistence

Runtime persistence is explicit. A persona is saved only when both conditions hold:

1. the manifest contains `policy.persistRuntime: true`; and
2. the operator supplies `--persist` during apply/deactivate or runs `config personaforge persist`.

The persistence sequence is:

1. apply and verify the live ConfigDB intent;
2. reject persistence if the active persona has drift;
3. run the native `config save -y` command;
4. read `/etc/sonic/config_db.json` and verify that the saved entries match the persona;
5. atomically write durable persona metadata and fsync its parent directory.

On node reboot, SONiC restores the saved ConfigDB. On FRR container restart, the templates and management processes read the same ConfigDB intent and gate the optional daemons again.

## 3. Demo personas

All profiles are under `code/sonic-buildimage/personaforge/profiles/`.

| Persona | Demonstrates | Notable runtime intent | Notable build intent |
|---|---|---|---|
| `l3-bgp-leaf-no-lag` | Reduced BGP leaf | Disable `bfdd`, LLDP, and unused service features | Remove teamd and most optional management/services; use the standard ONIE-compatible filesystem mode |
| `l3-bgp-bfd-leaf` | Fast-failure BGP leaf | Enable `bfdd` and LLDP | Retain LLDP; remove unused services; use the standard ONIE-compatible filesystem mode |
| `l3-multirouting-lab` | FRR daemon gating in management-framework mode | Enable `ospfd`, `pimd`, and `pathd`; disable `bfdd` | Remove teamd and optional management/services; use the standard ONIE-compatible filesystem mode |
| `l3-bgp-observability` | Observable BGP leaf | Enable LLDP, sFlow, SNMP, gNMI, and telemetry; disable `bfdd` | Retain observability packages; do not request filesystem reduction |

`l3-multirouting-lab` demonstrates daemon lifecycle only. Protocol configuration, neighbors, rendezvous points, or PCEP peers must still be configured through normal SONiC mechanisms.

### 3.1 `l3-bgp-bfd-leaf`

This persona demonstrates an affirmative FRR enable operation instead of reduction alone.

- Required capabilities: L3 forwarding, BGP, BFD, SSH/CLI, and platform monitoring.
- Omitted capabilities: DHCP relay, NAT, MACsec, MUX, sFlow, SNMP, gNMI, telemetry, and REST API.
- Runtime intent: set `FEATURE|lldp state enabled` when that row exists and set `FRR_DAEMON|bfdd admin_status enabled`.
- Build intent: set `INCLUDE_LLDP=y`, omit the catalog-controlled unused services, and retain SONiC's standard `BUILD_REDUCE_IMAGE_SIZE=n` archive mode. Link aggregation is not omitted, so the persona does not force `INCLUDE_TEAMD=n`.
- Routing modes: the catalog qualifies `bfdd` for classic and management-framework modes.
- Configuration boundary: enabling the daemon does not create BFD peers, sessions, or BGP BFD policy. Configure those separately when protocol-level testing is required.
- Persistence expectation: after explicit persistence, the BFD administrative row survives cold reboot and is consumed again whenever the BGP container starts.

### 3.2 `l3-multirouting-lab`

This persona demonstrates several optional FRR daemon gates in one BGP-container restart.

- Required capabilities: L3 forwarding, BGP, SSH/CLI, and platform monitoring.
- Omitted capabilities: link aggregation, DHCP relay, NAT, MACsec, MUX, sFlow, SNMP, gNMI, telemetry, and REST API.
- Runtime intent: disable LLDP and `bfdd`; enable `ospfd`, `pimd`, and `pathd`.
- Build intent: set the catalog-controlled optional service variables to `n` and retain SONiC's standard `BUILD_REDUCE_IMAGE_SIZE=n` archive mode. FRR remains a shared package, so this does not remove individual FRR binaries.
- Routing mode: use management-framework mode. The catalog qualifies `ospfd`, `pimd`, and `pathd` only for that mode.
- Configuration boundary: daemon startup alone does not create OSPF adjacencies, PIM neighbors/RPs, SR Policy, or PCEP peers. This profile demonstrates lifecycle wiring; protocol configuration and convergence are separate tests.
- Persistence expectation: all four `FRR_DAEMON` rows are saved together after verification and drive the next BGP-container render after restart or reboot.

The current persistence-focused runtime slice does not yet inventory and enforce routing mode before planning. For this demo, verify management-framework mode manually before apply; automatic mode rejection remains pending.

### 3.3 `l3-bgp-observability`

This persona is the contrast case: it retains visibility services rather than optimizing all optional services away.

- Required capabilities: L3 forwarding, BGP, SSH/CLI, platform monitoring, LLDP, sFlow, SNMP, gNMI, and telemetry.
- Omitted capabilities: link aggregation, DHCP relay, NAT, MACsec, MUX, and REST API.
- Runtime intent: enable the existing `lldp`, `sflow`, `snmp`, `gnmi`, and `telemetry` feature rows and disable `bfdd`.
- Build intent: set `INCLUDE_LLDP=y`, `INCLUDE_SFLOW=y`, `INCLUDE_SNMP=y`, `INCLUDE_SYSTEM_GNMI=y`, and `INCLUDE_SYSTEM_TELEMETRY=y`; omit unrelated services; leave `build.reduceFilesystem` false.
- Missing-row behavior: a build-pruned `FEATURE` row is skipped rather than fabricated. Test this profile on its matching image or on a standard image that contains the requested features.
- Persistence expectation: verified feature and BFD rows are written to the saved SONiC configuration and checked again through `show personaforge status` after restart/reboot.

All three profiles use `persistRuntime: true`, but none saves automatically. Use `--persist` or `config personaforge persist`. They also use `allowNodeReboot: false`: this prevents PersonaForge from selecting reboot as an activation action and does not prevent already-persisted configuration from surviving an operator-initiated reboot.

## 4. Fast source-level validation

Run from the SONiC buildimage repository:

```bash
cd /home/ubuntu/OCP-Hackathon-2026/Persona-Forge/code/sonic-buildimage
PYTHONPATH=src/personaforge python3 -m unittest discover -s src/personaforge/tests -v
```

Expected result: all tests pass. The suite validates schemas, deterministic builds, conflict handling, all shipped profiles, FRR gating, runtime planning, CLI registration, apply/persist/deactivate behavior, drift handling, and saved-config verification.

## 5. Inspect a persona build without building an image

The following generates the build artifacts in `/tmp`, leaving the source tree clean:

```bash
cd /home/ubuntu/OCP-Hackathon-2026/Persona-Forge/code/sonic-buildimage
PROFILE=l3-bgp-bfd-leaf
OUT=/tmp/personaforge-manual-$PROFILE
SOURCE_COMMIT=$(git rev-parse HEAD)
mkdir -p "$OUT"
PYTHONPATH=src/personaforge python3 scripts/personaforge-build generate \
  --profile "personaforge/profiles/$PROFILE.yaml" \
  --catalog src/personaforge/catalogs/202605.yaml \
  --source-commit "$SOURCE_COMMIT" \
  --platform broadcom \
  --output-dir "$OUT"
ls -1 "$OUT"
sed -n '1,200p' "$OUT/personaforge.mk"
python3 -m json.tool "$OUT/build-plan.json"
```

Change `PROFILE` to each name in the table above. Confirm that:

- every profile has a different deterministic build key;
- `l3-bgp-leaf-no-lag` sets `INCLUDE_TEAMD = n` and `INCLUDE_LLDP = n`;
- `l3-bgp-bfd-leaf` sets `INCLUDE_LLDP = y`, sets both `INCLUDE_SYSTEM_GNMI = n` and `INCLUDE_SYSTEM_TELEMETRY = n`, but does not remove teamd;
- `l3-multirouting-lab` removes teamd and LLDP;
- `l3-bgp-observability` sets both `INCLUDE_SYSTEM_GNMI = y` and `INCLUDE_SYSTEM_TELEMETRY = y` with its other observability build variables;
- no platform-independent demo profile emits `BUILD_REDUCE_IMAGE_SIZE`; the SONiC baseline retains its standard `n` default and gzip-compatible ONIE archive path.

To demonstrate conflict protection, put `INCLUDE_TEAMD = y` in `rules/config.user` temporarily and select `l3-bgp-leaf-no-lag`. Generation must fail because that persona requires `INCLUDE_TEAMD = n`. Restore the pre-test `rules/config.user` content immediately afterward; do not use this conflict test in a working tree where that file contains changes you cannot safely reproduce.

## 6. Build a platform image

Use the normal SONiC build environment and select one persona per image. PersonaForge does not maintain a platform allowlist. For a Broadcom build, use the normal platform and target supported by your SONiC tree, for example:

```bash
cd /home/ubuntu/OCP-Hackathon-2026/Persona-Forge/code/sonic-buildimage
make configure PLATFORM=broadcom
make PERSONAFORGE_PROFILE=l3-bgp-leaf-no-lag target/sonic-broadcom.bin
```

The additional demo selections are:

```bash
make PERSONAFORGE_PROFILE=l3-bgp-bfd-leaf target/sonic-broadcom.bin
make PERSONAFORGE_PROFILE=l3-multirouting-lab target/sonic-broadcom.bin
make PERSONAFORGE_PROFILE=l3-bgp-observability target/sonic-broadcom.bin
```

Replace `broadcom` and `target/sonic-broadcom.bin` with the normal values for the target platform when they differ. Run these as separate builds rather than concurrently. Archive or label each output before building the next selection. Do not reuse conclusions from one image or platform for another; both profile and selected platform participate in the build identity.

After the build, inspect:

```bash
find target/personaforge/generated/l3-bgp-leaf-no-lag -maxdepth 2 -type f -print
```

Replace the profile directory in that command for each additional selection. The generated directory should contain `personaforge.mk`, `manifest.normalized.json`, `catalog.json`, `build-plan.json`, and `input.json` beneath the build-key directory.

Before installing a generated binary through ONIE, verify that its embedded Docker archive follows SONiC's standard gzip path:

```bash
PAYLOAD_DIR=$(mktemp -d)
sed -e '1,/^exit_marker$/d' target/sonic-broadcom.bin \
  | tar xf - -C "$PAYLOAD_DIR" installer/fs.zip
unzip -p "$PAYLOAD_DIR/installer/fs.zip" dockerfs.tar.gz | gzip -t
```

The final command must exit with status zero. This check prevents selecting SONiC's `docker_inram`-specific Zstandard archive path for a normal ONIE platform.

## 7. Runtime test on a SONiC node

Run these commands inside a SONiC image built from this source. They are not expected to work on the Ubuntu source-build host because that host does not provide SONiC ConfigDB, services, or CLI dependencies.

### 7.1 Discover the commands

```bash
config personaforge --help
show personaforge --help
show personaforge status
```

Initially, status should be inactive unless a previous test left persona metadata.

### 7.2 Preview without changing the node

```bash
show personaforge plan l3-bgp-bfd-leaf
show personaforge plan l3-bgp-bfd-leaf --json
```

The plan shows current and desired values plus whether each entry changes. For the BFD persona, expect `FRR_DAEMON|bfdd admin_status enabled`. A feature already pruned from the image has no runtime owner and is intentionally not recreated by the planner.

### 7.3 Apply live, without persistence

```bash
sudo config personaforge apply l3-bgp-bfd-leaf --allow-disruptive -y
show personaforge status --detail
show personaforge drift
sonic-db-cli CONFIG_DB HGETALL 'FRR_DAEMON|bfdd'
systemctl is-active bgp
docker exec bgp supervisorctl status
```

Expected observations:

- the persona is `active` and `Persisted` is `no`;
- drift is empty;
- `bfdd` is enabled in ConfigDB and present in the BGP container process list;
- `bgp.service` is active after the authorized restart.

Applying the same profile again should report that it is already active. Applying another profile should be rejected until the current profile is deactivated.

### 7.4 Persist separately

```bash
sudo config personaforge persist -y
show personaforge status --detail
sudo python3 -m json.tool /var/lib/personaforge/active.json
sudo sonic-db-cli CONFIG_DB HGETALL 'FRR_DAEMON|bfdd'
sudo grep -A4 -B1 'FRR_DAEMON' /etc/sonic/config_db.json
```

Status should now show `Persisted yes` and `Saved config matches yes`.

The equivalent one-step operation is:

```bash
sudo config personaforge apply l3-bgp-bfd-leaf --allow-disruptive --persist -y
```

### 7.5 Verify container-restart persistence

```bash
sudo systemctl restart bgp
systemctl is-active bgp
docker exec bgp supervisorctl status
show personaforge status --detail
show personaforge drift
```

The selected FRR daemon state should be reconstructed from ConfigDB, and drift should remain empty.

### 7.6 Verify node-reboot persistence

```bash
sudo reboot
```

After reconnecting:

```bash
show personaforge status --detail
show personaforge drift
sonic-db-cli CONFIG_DB HGETALL 'FRR_DAEMON|bfdd'
systemctl is-active bgp
docker exec bgp supervisorctl status
```

The ConfigDB intent and daemon state should match the persisted persona. `show personaforge status` falls back to durable metadata when `/run/personaforge/active.json` is absent after reboot.

### 7.7 Demonstrate drift detection

Perform this only on a disposable lab node:

```bash
sudo sonic-db-cli CONFIG_DB HSET 'FRR_DAEMON|bfdd' admin_status disabled
show personaforge drift
sudo config personaforge persist -y
```

The drift command should report desired `enabled` versus actual `disabled`, and persistence should be refused. Restore the test by deactivating only after putting the live value back to the persona's desired state:

```bash
sudo sonic-db-cli CONFIG_DB HSET 'FRR_DAEMON|bfdd' admin_status enabled
show personaforge drift
sudo config personaforge deactivate --allow-disruptive --persist -y
show personaforge status
```

### 7.8 Test each additional persona

Always deactivate the current persona before applying a different one. For persisted tests, use `--persist` on both apply and deactivate so the saved configuration follows the intended state.

#### 7.8.1 BFD leaf

Use an image that retains BFD and LLDP:

```bash
show personaforge plan l3-bgp-bfd-leaf --json
sudo config personaforge apply l3-bgp-bfd-leaf --allow-disruptive --persist -y
sonic-db-cli CONFIG_DB HGET 'FRR_DAEMON|bfdd' admin_status
sonic-db-cli CONFIG_DB HGET 'FEATURE|lldp' state
docker exec bgp supervisorctl status | grep bfdd
show personaforge status --detail
show personaforge drift
```

Expected results are `enabled` for both queried values, a running `bfdd` supervisor program, persisted status, and no drift. This proves administrative lifecycle only. Add normal SONiC BFD/BGP configuration before testing BFD session establishment or failure detection.

Clean up before the next profile:

```bash
sudo config personaforge deactivate --allow-disruptive --persist -y
```

#### 7.8.2 Multi-routing lab

Use a management-framework-mode image and verify the routing mode through the normal image configuration before apply. Then run:

```bash
show personaforge plan l3-multirouting-lab --json
sudo config personaforge apply l3-multirouting-lab --allow-disruptive --persist -y
sonic-db-cli CONFIG_DB HGETALL 'FRR_DAEMON|bfdd'
sonic-db-cli CONFIG_DB HGETALL 'FRR_DAEMON|ospfd'
sonic-db-cli CONFIG_DB HGETALL 'FRR_DAEMON|pimd'
sonic-db-cli CONFIG_DB HGETALL 'FRR_DAEMON|pathd'
docker exec bgp supervisorctl status | grep -E 'bfdd|ospfd|pimd|pathd'
docker exec bgp sh -c "grep -E 'ospfd|pimd|pathd|bfdd' /etc/supervisor/conf.d/supervisord.conf"
show personaforge status --detail
show personaforge drift
```

Expected ConfigDB intent is `bfdd=disabled` and `ospfd=pimd=pathd=enabled`. The enabled daemons should appear in the rendered supervisor configuration and process status; disabled `bfdd` should not be a required/running program. An empty protocol neighbor/session table is not a failure because this persona does not generate protocol configuration.

Clean up before the next profile:

```bash
sudo config personaforge deactivate --allow-disruptive --persist -y
```

#### 7.8.3 Observability leaf

Use the matching `l3-bgp-observability` image, or first confirm the standard image contains all requested `FEATURE` rows:

```bash
for feature in lldp sflow snmp gnmi telemetry; do
  sonic-db-cli CONFIG_DB HGETALL "FEATURE|$feature"
done
show personaforge plan l3-bgp-observability --json
sudo config personaforge apply l3-bgp-observability --allow-disruptive --persist -y
for feature in lldp sflow snmp gnmi telemetry; do
  sonic-db-cli CONFIG_DB HGET "FEATURE|$feature" state
done
sonic-db-cli CONFIG_DB HGET 'FRR_DAEMON|bfdd' admin_status
show personaforge status --detail
show personaforge drift
```

Expected results are `enabled` for each retained feature, `disabled` for `bfdd`, persisted status, and no ConfigDB drift. Also inspect `docker ps` and the normal service-specific show commands for the image. Current PersonaForge verification does not yet prove every feature container's operational convergence, so record those observations separately.

For each persona, repeat Sections 7.5 and 7.6 to test BGP-container restart and cold-node reboot persistence, then deactivate it before moving to another profile.

## 8. What is still pending

- Full SONiC platform image-build evidence for every demo persona.
- End-to-end boot, container-restart, and node-reboot evidence on the selected Broadcom or other target platform.
- Implementations of the catalog's declared dependency probes, including configured sessions and management-path consumers.
- Runtime routing-mode inventory and automatic rejection of management-framework-only daemon controls in classic mode.
- Rich verification for container/process health and protocol convergence; current apply verification checks ConfigDB equality and BGP service activity for FRR changes.
- Transactional multi-step rollback, boot-time reconciliation, automatic recovery, and failure journals.
- Target-specific hardware, ASIC, and multi-ASIC qualification; these are no longer blocked by the persona contract but remain unverified.
- A supported direct transition between different active personas; currently deactivate first.

Until dependency probes and convergence verification are implemented, use a clean, disposable lab switch, confirm its normal SONiC platform support and routing mode, and inspect the plan before applying a persona.
