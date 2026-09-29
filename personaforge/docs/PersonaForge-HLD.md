# PersonaForge High-Level Design

> **Project:** SONiC OCP Hackathon 2026 — PersonaForge
> **Target:** Community SONiC `sonic-buildimage` `202605`
> **Status:** Implementation specification
> **Reviewed:** 2026-09-28
> **Normative requirements:** [PersonaForge Requirements Specification](PersonaForge-Requirements.md)

---

## 1. Design scope and verified baseline

This is the single implementation HLD for PersonaForge. It covers the shared compiler, runtime realization, build realization, native SONiC CLI, and evidence pipeline. The Requirements specification defines externally visible behavior; this document defines component ownership and SONiC/FRR integration.

### 1.1 Baseline identity

| Item | Verified value |
|---|---|
| Delivery branch | `mh-csonic/sonic-buildimage:rathnasabapathyv/2026_hackathon_persona` |
| SONiC source baseline | `03a90ea321b3d9f71ae88ae23d4ccd146225e95c`, matching the reviewed mirror `202605` ref |
| PersonaForge implementation revision | The commit containing this document on the delivery branch; use Git identity rather than embedding a self-referential hash here |
| Baseline `sonic-utilities` revision | `bf72b0aead74519e4a2c973902fa2f844929eac2` |
| PersonaForge `sonic-utilities` revision | `be94ea1332c37f726504f4da7522e2a30c43abd7` on `rathnasabapathyv/2026_hackathon_persona` |
| Pinned FRR revision | `4cb6d9e6bfe4ad503d1fab21e6f665804b0649ac` |

The delivered commit leaves the upstream FRR gitlink unchanged. Developer-local submodule checkouts, generated output, and unrelated untracked files are not part of the PersonaForge change. Qualification must use committed superproject and submodule identities rather than local worktree state.

### 1.2 Code constraints that drive the design

| Verified 202605 behavior | Design consequence |
|---|---|
| Optional containers/packages are already controlled by build variables in `rules/config` and component rules. | Build mode generates verified existing inputs instead of adding a packaging system. |
| Several variables, including `INCLUDE_SFLOW` and `BUILD_REDUCE_IMAGE_SIZE`, use unconditional `=` defaults. | PersonaForge's generated include must be loaded after `rules/config` and `rules/config.user`, with explicit conflict checks. |
| Top-level `Makefile` dispatches normal targets to `Makefile.work`; command-line variables propagate to sub-make. | `PERSONAFORGE_PROFILE` is accepted at the normal top-level invocation and implemented in `Makefile.work`. |
| ConfigDB `FEATURE` controls containers, not arbitrary child processes. | `FEATURE` is one runtime adapter; FRR daemon state has a separate contract. |
| `docker-fpm-frr/docker_init.sh` runs `sonic-cfggen -d` to Jinja-render BGP supervisor and critical-process files at every container start. | The modeled `FRR_DAEMON` table now drives restart-activated startup and readiness for allowlisted optional daemons; missing/default data preserves baseline behavior. |
| `frrcfgd` connects to a known daemon set and fails after missing-socket retries. | It must filter intentionally disabled optional daemons from that set. |
| Classic `bgpcfgd` can directly start `bfdd`. | Both BFD manager creation and direct-spawn fallback must honor `FRR_DAEMON|bfdd`. |
| Core routing and FPM processes share the BGP container. | Optional child daemons may be controlled; BGP container omission and core process disable are prohibited for the primary persona. |
| `config` and `show` are Click console scripts registered in `sonic-utilities`. | Native PersonaForge groups are implemented there; the current slice also contains bounded apply/persist orchestration in the `config` module. |
| `config save` writes live ConfigDB to `/etc/sonic/config_db.json`, flushes and `fsync`s it; `config reload` validates, replaces ConfigDB, and normally restarts services. | The implemented slice persists only after live ConfigDB verification and verifies the saved file before writing durable persona metadata. A new table requires a YANG model or reload validation aborts. |
| Boot `config-setup` loads saved ConfigDB and sets `CONFIG_DB_INITIALIZED`; `bgp.service` requires and follows `config-setup.service` and renders from the live DB. | Saved intent can be reconstructed at cold boot when the schema and consumers are installed before boot. |
| `featured` consumes ConfigDB `FEATURE`, invokes service lifecycle, and publishes observed feature state to STATE_DB; telemetry and `frr_bmp` are explicit exclusions. | The current slice writes validated ConfigDB intent and verifies ConfigDB equality. STATE_DB, unit, container, and exception-specific convergence verification remains future work. |

### 1.3 Prototype versus remaining implementation

| Area | Status |
|---|---|
| `FRR_DAEMON` YANG model | Implemented under `src/sonic-yang-models/yang-models/` and packaged by `src/sonic-yang-models/setup.py` |
| Supervisor and critical-process gating | Implemented for `bfdd`, `ospfd`, `pimd`, and `pathd`; core processes remain unconditional |
| `frrcfgd` optional-daemon filtering | Implemented from ConfigDB desired state; protected/unknown daemon disable requests are rejected |
| Classic `bgpcfgd` BFD guard | Implemented at manager selection and direct-spawn fallback |
| Schema/catalog/compiler | PF-Contract schema, safe loader, typed normalized manifest, digest, 202605 catalog validator, four shipped profiles, and unit tests implemented in this change |
| Inventory and planner | A bounded catalog-driven runtime planner is implemented over live `FEATURE` and `FRR_DAEMON` tables. Routing-mode inventory, operational inventory, configured-dependency probes, and transitive dependency evidence remain pending. |
| Runtime apply and verification | Validated ConfigDB writes, explicit disruption authorization, BGP restart, BGP active-state check, ConfigDB equality verification, active metadata, persistence, drift, idempotency, and deactivation are implemented. |
| Transaction and recovery | Global lock, transaction journal, automatic failure rollback, convergence verification, pending reboot recovery, controller, and boot verifier are not implemented. |
| Native SONiC CLI and image packaging | Persistence-focused `apply`, `persist`, `deactivate`, `status`, `plan`, and `drift` commands and runtime wheel packaging are implemented; inventory, report, footprint, transaction rollback, and full image qualification remain pending |
| Make profile integration | Implemented with an inert-by-default `PERSONAFORGE_PROFILE` knob, pinned input validation, deterministic keyed outputs, and conflict checks; post-build artifact verification remains unimplemented |
| Footprint capture/report | Not implemented |
| FRR-native live administrative state | Optional proof of concept; not implemented |

## 2. Architecture

### 2.1 Context and execution boundaries

~~~text
 native config/show                          make PERSONAFORGE_PROFILE=<name>
        |                                                |
 runtime manifest                                named build manifest
        \                                                /
         +--------------------+-------------------------+
                              |
                    schema + release catalog
                              |
                              v
                   bounded deterministic planner
                              |
                       immutable plan
                       /            \
                      v              v
          validated CLI apply     Make fragment generator
              |          |                 |
              v          v                 v
          ConfigDB    BGP restart       normal image build
           writes     when required    (verification pending)
              \          /                 /
               +--------+-----------------+
                        |
                        v
                 status and evidence
~~~

Runtime and build share data contracts but never invoke one another. A switch command does not run the build toolchain. A build invocation does not mutate a running switch.

### 2.2 Components

| Component | Responsibility | Primary output |
|---|---|---|
| Manifest loader | Safe YAML load, strict schema, normalization, digest | `NormalizedManifest` |
| Catalog loader | Select and validate release controls, components, and declared probes | `ReleaseCatalog` |
| Runtime table reader | Read current `FEATURE` and `FRR_DAEMON` values | Planning input |
| Runtime planner | Resolve catalog-mapped desired fields and captured previous values | `RuntimePlan` |
| Native CLI implementation | Plan/render, validated writes, BGP restart, verification, persistence, drift, and deactivation | Text/JSON, metadata, and exit status |
| Build generator | Convert a build plan into catalog-limited Make values | `personaforge.mk` and identity |
| Future inventory/transaction/adapters | Dependency probes, operational inventory, journal, convergence, rollback, and recovery | Not implemented in this slice |
| Future artifact/evidence pipeline | Prove image contents, boot behavior, footprint, and smoke tests | Not implemented in this slice |

### 2.3 Ownership rules

- The manifest owns deployment intent, not implementation commands.
- The release catalog owns all release-specific mappings, protected sets, probes, activations, and timeouts.
- Actual ConfigDB/systemd/Docker/FRR/build state owns observed truth.
- The planner is pure and performs no mutation.
- The current `config` module owns bounded orchestration; the shared runtime module owns plan, metadata, drift, and inverse-action contracts.
- A future coordinator/adapter layer will own transaction state, convergence verification, and rollback; it must not be inferred from the current CLI.
- FRR owns FRR process health. A SONiC bridge may translate ConfigDB intent; FRR must not depend on Redis.
- Reports are outputs and never become control input.

## 3. Shared core design

### 3.1 Package structure

~~~text
src/personaforge/
  setup.py
  personaforge/
    __init__.py
    _yaml.py
    build.py
    catalog.py
    errors.py
    manifest.py
    runtime.py
  schema/persona-v1alpha1.json
  schema/catalog-v1.json
  catalogs/202605.yaml
  tests/

personaforge/
  IMPLEMENTATION-AND-MANUAL-TEST-GUIDE.md
  docs/
    PersonaForge-HLD.md
    PersonaForge-Requirements.md
  profiles/
    l3-bgp-leaf-no-lag.yaml
    l3-bgp-bfd-leaf.yaml
    l3-multirouting-lab.yaml
    l3-bgp-observability.yaml
~~~

The core is a SONiC Python wheel installed in the host image. The build helper imports the same manifest, catalog, and build-contract modules from the source tree. Runtime catalogs, schemas, and named profiles are installed read-only under `/usr/share/personaforge/`; mutable metadata is stored separately under `/run/personaforge` or `/var/lib/personaforge`.

#### Shipped demo persona design

The four shipped profiles share the pinned `202605` release boundary without a platform or ASIC-count allowlist. They all retain L3 forwarding, BGP, SSH/CLI, and platform monitoring, authorize disruptive actions only when the CLI also opts in, prohibit PersonaForge-initiated node reboot, and permit explicit runtime persistence. They are intentionally separate immutable manifests so their normalized digest and build key identify the exact demonstration intent. The selected SONiC platform remains in the build identity for cache separation, while actual hardware qualification remains target-specific.

| Profile | Design purpose | Capability/override design | Build realization | Runtime realization and constraint |
|---|---|---|---|---|
| `l3-bgp-leaf-no-lag` | Primary minimal BGP leaf | Omits link aggregation and optional service/management capabilities; explicitly disables LLDP and `bfdd` | Removes catalog-controlled optional artifacts and selects reduced filesystem | Disables existing applicable `FEATURE` rows and BFD; demonstrates reduction |
| `l3-bgp-bfd-leaf` | BGP leaf with fast failure detection | Adds required `bfd`; explicitly enables LLDP and `bfdd`; leaves link aggregation at its default | Retains LLDP/teamd, removes unused optional services, and selects reduced filesystem | Exercises the FRR enable path in classic or management-framework routing mode; BFD peers/sessions remain normal SONiC configuration |
| `l3-multirouting-lab` | Optional FRR daemon lifecycle demonstration | Explicitly enables `ospfd`, `pimd`, and `pathd`, disables `bfdd` and LLDP, and omits link aggregation and optional services | Removes catalog-controlled service artifacts and selects reduced filesystem; individual FRR binaries remain in the shared FRR package | Requires management-framework routing mode. It starts eligible daemons but does not synthesize OSPF, PIM, SR Policy, or PCEP configuration |
| `l3-bgp-observability` | BGP leaf retaining operational visibility services | Requires and explicitly enables LLDP, sFlow, SNMP, gNMI, and telemetry; disables `bfdd`; omits link aggregation and unrelated services | Retains observability artifacts and deliberately leaves filesystem reduction off, providing a contrast to reduced profiles | Exercises multiple `FEATURE` enable intents plus FRR disable. Only feature rows present in the built image are runtime owners |

The BFD and observability personas use explicit `enabled` overrides so a plan clearly shows their affirmative intent. A build-pruned `FEATURE` row is never fabricated at runtime. Therefore, runtime demonstrations must use an image whose selected build persona retains the feature being enabled, or a standard image that already contains it.

Profile changes are not an in-place merge. The current CLI requires the active profile to be deactivated before a different profile is applied, preserving the captured pre-apply values used by `deactivate`.

### 3.2 Data contracts

`NormalizedManifest` contains the exact canonical object and SHA-256 defined by Requirements Section 4. It never contains executable strings.

`ReleaseCatalog` is a versioned data file with this conceptual structure:

~~~yaml
catalogVersion: 1
sonicRelease: "202605"
components:
  teamd:
    protected: false
    runtimeAdapter: feature
    featureName: teamd
    buildVariable: INCLUDE_TEAMD
    dependencyProbes: [portchannel-present]
    verify: [feature-state, systemd, container]
  bfdd:
    protected: false
    runtimeAdapter: frr-daemon
    daemonName: bfdd
    supportedRoutingModes: [classic, management-framework]
    dependencyProbes: [bfd-config, bfd-consumers]
    activation: [frr-live, bgp-restart, node-reboot]
~~~

Catalog validation rejects unknown components, invalid runtime adapters, feature mappings without feature names, and FRR daemon mappings outside the bounded allowlist. Dependency-probe and verification names are declarative catalog data in the current slice; their executors are pending.

The implemented runtime input is a bounded snapshot of the live `FEATURE` and `FRR_DAEMON` tables. It does not yet include systemd, container, STATE_DB, routing-mode, protocol-session, or configured-dependency inventory. The implemented build input records the current 40-character source commit, selected platform, manifest/catalog/generator digests, and resolved settings. The release catalog does not pin a self-referential implementation commit.

`RuntimePlan` is immutable and contains:

~~~text
profile and manifest/catalog identity
ordered ConfigDB field actions with reason, previous value, and desired value
manifest disruption and persistence policy flags
~~~

`BuildContract` contains the deterministic build key, catalog-limited Make settings, and build decisions. Full operational inventory, dependency evidence, activation selection, rollback proof, and artifact evidence remain target contracts.

### 3.3 Resolver algorithm

1. Validate and normalize the manifest and catalog.
2. Enforce release compatibility; do not reject a selected SONiC platform or ASIC topology through the persona contract.
3. Expand required capabilities into a protected component set.
4. Map omitted capabilities and explicit overrides through catalog-known controls.
5. For runtime, resolve sorted `FEATURE` and `FRR_DAEMON` field actions from live table values, skipping a missing build-pruned `FEATURE` row.
6. For build, emit only catalog-declared variables and reject conflicts with explicit build settings.
7. Calculate deterministic runtime/build identities and preserve reasons for every emitted action or decision.

Routing-mode enforcement, configured-dependency probes, operational presence checks, activation selection, and transitive action ordering are pending. The implemented resolver must not be described as providing those checks.

### 3.4 Core API and errors

There is no unified `personaforge.api` module in the current slice. The installed package exports bounded contract functions used by the CLI:

~~~text
load_manifest()
load_catalog()
resolve_build_contract()
resolve_runtime_plan()
calculate_drift()
inverse_actions()
create_active_metadata()
read_metadata()
~~~

The native CLI currently owns validated writes, BGP restart, post-write verification, save verification, and user-facing error conversion. A stable facade, typed error categories, transaction coordinator, and report/evidence API remain target design.

## 4. Runtime design

### 4.1 Target transaction lifecycle — pending

The following state machine is the target for a later transactional/rollback phase. It is not implemented by the current persistence-focused CLI.

~~~text
PLANNED -> LOCKED -> REVALIDATED -> SNAPSHOTTED -> APPLYING
                                                    |
                         +--------------------------+------------------+
                         v                                             v
                     VERIFYING                                      FAILED
                         |                                             |
                         v                                             v
              COMMITTED or PERSISTED                            ROLLING_BACK
                                                                       |
                                                         ROLLED_BACK or DEGRADED
~~~

Execution contract:

1. acquire `/run/personaforge/lock`;
2. reload manifest/catalog and refresh inventory;
3. reject if the new plan differs materially from the approved plan;
4. create a transaction directory and atomically store normalized manifest, plan, inventory, and snapshots;
5. execute ordered actions with deadlines;
6. verify adapter postconditions plus persona health;
7. persist only when requested and verified;
8. on failure, restore completed actions in reverse order and verify recovery;
9. atomically write the final result and release the lock.

Mutating adapters are not called by the planner or `show` API. Reapplying a converged persona creates a successful no-op record.

### 4.2 Target adapter interface — pending

The future runtime adapters are intended to implement:

~~~text
probe(component, context) -> Observation
snapshot(action, context) -> Snapshot
apply(action, context) -> ApplyResult
verify(action, context, deadline) -> Observation
rollback(action, snapshot, context) -> RollbackResult
~~~

The command runner accepts argument arrays only, captures bounded stdout/stderr, enforces timeouts, and redacts protected data. An adapter cannot persist configuration independently of the coordinator.

### 4.3 Implemented SONiC feature handling

The current planner handles only present catalog-qualified `FEATURE` rows. A feature row missing from the installed image is treated as build-pruned and is not recreated.

- Capture the previous planned field value in active metadata.
- Write changed rows through `ValidatedConfigDBConnector`.
- Re-read ConfigDB and require field equality after apply.
- Restore the captured field values when the operator runs `deactivate`.
- Skip protected components and reject an explicit override that disables a required component.

The current slice does not invoke `config feature state --block`, verify STATE_DB/systemd/container convergence, execute dependency probes, or automatically roll back a failed multi-action apply. Those behaviors remain target adapter work.

### 4.4 FRR desired-state contract

The ConfigDB/YANG contract is:

~~~text
FRR_DAEMON|bfdd   admin_status = default|enabled|disabled
FRR_DAEMON|ospfd  admin_status = default|enabled|disabled
FRR_DAEMON|pimd   admin_status = default|enabled|disabled
FRR_DAEMON|pathd  admin_status = default|enabled|disabled
~~~

Missing row/table and `default` preserve existing behavior. All readers use the same bounded allowlist.

At BGP-container start:

- `supervisord.conf.j2` omits a supported optional daemon only when explicitly disabled and otherwise retains existing mode conditions;
- `critical_processes.j2` uses the identical predicate;
- management-framework `frrcfgd` excludes disabled optional VTY clients while retaining core clients;
- classic `bgpcfgd` skips the BFD manager/direct spawn when `bfdd` is disabled.

The catalog declares dependency probes and supported routing modes, but the current runtime planner does not execute or enforce them. Operators must use a clean lab configuration on the selected platform and manually confirm management-framework mode for `ospfd`, `pimd`, and `pathd`. The catalog/YANG allowlist prevents arbitrary or core daemon names. Probe execution and automatic routing-mode rejection remain pending.

### 4.5 FRR activation design

#### Implemented BGP restart path and target completion

1. Snapshot all affected `FRR_DAEMON` rows and BGP/routing health.
2. Write candidate rows through a validated ConfigDB interface.
3. Restart the SONiC BGP service/container, not the node.
4. Wait for container health, required supervisor processes, configuration owner, BGP adjacency, expected routes, and FPM/route-programming recovery.
5. On failure, restore rows, restart BGP again, verify recovery, and mark rolled back or degraded.

The current slice implements steps 2 and 3, then requires `bgp.service` to become active and re-verifies the planned ConfigDB fields. Steps 1, 4, and 5 are target behavior: routing-health snapshots, adjacency/route/FPM convergence, and automatic restore/restart rollback are not implemented. A running service plus ConfigDB equality is therefore the current bounded success criterion, not full protocol convergence.

#### FRR-native live control — optional proof of concept

The FRR change belongs in `watchfrr` because it already owns daemon start/restart supervision. The proposed interface must:

- expose administrative enable/disable for the allowlist;
- serialize transitions with restart handling;
- on disable, suppress restart before stopping and remove the daemon from readiness/down accounting;
- on enable, start and wait for socket/health before reporting success;
- distinguish administrative from operational state;
- preserve existing behavior when no administrative override exists.

A SONiC adapter subscribes to validated `FRR_DAEMON` intent, invokes the FRR interface, and publishes operational result. Raw `supervisorctl stop` is not a supported implementation.

#### Node reboot activation — pending

Reboot activates the same persisted desired state and startup consumers. It is eligible only when the installed image already contains all controls, narrower activation is unavailable/unqualified, and both manifest and CLI authorize it.

The current CLI never selects or initiates a node reboot. Persisted ConfigDB intent can survive an operator-initiated cold reboot through normal SONiC boot loading, but no PersonaForge boot verifier or automatic recovery exists. The coordinator behavior described above remains future design, and reboot is not a substitute for missing code.

### 4.6 Persistence and operational state

~~~text
/run/personaforge/lock
/run/personaforge/active.json                         # current-boot, non-persistent intent
/run/personaforge/transactions/<transaction-id>/     # ordinary transient records
/var/lib/personaforge/active.json                    # persisted active identity only
/var/lib/personaforge/transactions/<transaction-id>/
  manifest.normalized.json
  inventory.before.json
  plan.json
  snapshot.json
  result.json
  recovery.json
~~~

Only the two `active.json` paths are implemented. The lock and transaction directories shown above are reserved target paths for the pending transaction/recovery phase.

ConfigDB owns `FEATURE` and `FRR_DAEMON` desired state. In the implemented slice, `/run/personaforge/active.json` owns current-boot persona identity and `/var/lib/personaforge/active.json` owns explicitly persisted identity; neither substitutes for ConfigDB rows. STATE_DB remains SONiC operational state but is not currently consumed by PersonaForge verification. Transaction directories and durable pending/last-known-good records are reserved for future work.

Implemented persistence runs only after verification: invoke `config save -y`, verify the saved file contains the candidate fields, then atomically update `/var/lib/personaforge/active.json`. Pre-verification reboot staging, pending markers, complete snapshots, attempt counters, and recovery deadlines are target design and are not present in this slice.

#### Implemented persistence slice

The current native CLI implements the following bounded flow:

1. Resolve the named installed profile and catalog against live `FEATURE` and `FRR_DAEMON` tables.
2. Atomically write an `applying` record to `/run/personaforge/active.json`, including desired actions and captured pre-apply field values.
3. Write changed rows through `ValidatedConfigDBConnector`; build-pruned `FEATURE` rows are not recreated.
4. When `FRR_DAEMON` changes, require `--allow-disruptive`, restart `bgp.service`, and require it to return active.
5. Re-read ConfigDB and require every planned field to equal its desired value, then mark the `/run` record active.
6. Without persistence, stop here. Live ConfigDB drives later BGP-container renders during the current boot, while a cold reboot returns to the last saved SONiC configuration.
7. With manifest `persistRuntime: true` and CLI `--persist` (or explicit `config personaforge persist`), execute `config save -y`, re-read `/etc/sonic/config_db.json`, reject any saved-row drift, then atomically write `/var/lib/personaforge/active.json` and update the `/run` record as persisted.
8. `deactivate` restores captured pre-apply fields; `deactivate --persist` saves that restored ConfigDB and removes durable active metadata.

This slice verifies ConfigDB equality and `bgp.service` activity. Adjacency, route/FPM, STATE_DB/container health, whole-Docker/database restart, automatic reconciliation, transaction rollback, pending reboot recovery, and boot-verifier qualification remain pending. There is no `personaforged` or `personaforge-boot-verify.service` in the implemented slice.

Files are root-owned, not world-writable, and use atomic write/rename plus directory sync where recovery depends on durability. Image-upgrade migration is not assumed; a new image must be re-inventoried and re-planned.

### 4.7 Implemented restart and boot behavior

| Event | Source of truth and owner | Ordering and verification | Failure behavior |
|---|---|---|---|
| Optional feature container/service restart | Live ConfigDB `FEATURE`; existing SONiC feature lifecycle owns convergence. | PersonaForge can report ConfigDB drift but does not currently observe STATE_DB, unit, or container health. | No automatic PersonaForge reconciliation or rollback. |
| BGP restart | Live ConfigDB `FRR_DAEMON`; BGP startup renders supervisor and critical-process files, and configuration owners consume the same allowlist. | PersonaForge-triggered restart requires `bgp.service` active plus ConfigDB equality. | Apply reports failure; automatic restoration/restart rollback is pending. |
| ConfigDB reload | Reloaded ConfigDB becomes live desired state. The installed YANG model permits modeled `FRR_DAEMON` rows. | `show personaforge drift` compares the active metadata with the reloaded tables. | Report-only; no automatic reconciliation. |
| Cold reboot after persistence | `config-setup` loads `/etc/sonic/config_db.json`; BGP startup renders the saved FRR intent. | `show personaforge status` falls back to `/var/lib/personaforge/active.json` and reports live/saved drift. | No boot verifier or automatic recovery. |
| Cold reboot without persistence | Previously saved ConfigDB is restored; `/run` metadata is cleared. | There is no durable active record unless an earlier persisted persona exists. | Current code has no boot-time cleanup/reconciliation service. |
| Warm reboot and image upgrade | Not qualified. | No PersonaForge activation path selects warm reboot, and metadata migration across image upgrade is unsupported. | Re-plan on the new image; do not infer support. |

There is no `personaforged` controller and no `personaforge-boot-verify.service` in this slice. Event subscriptions, periodic reconciliation, pending/LKG state, bounded boot recovery, and observe-before-act transaction recovery remain target design.

### 4.8 Implemented persistence control matrix

| Control | Selective container restart | BGP restart | Cold node reboot |
|---|---|---|---|
| `FEATURE` | Existing SONiC feature lifecycle consumes live ConfigDB; PersonaForge checks ConfigDB only | BGP restart does not change unrelated feature intent | State survives only after verified `config save`; PersonaForge reports ConfigDB/saved drift but does not verify container convergence |
| FRR restart-activated | Not applicable | Live `FRR_DAEMON` is rendered at BGP start; current verification is BGP service activity plus ConfigDB equality | Saved rows are loaded before BGP and rendered; no PersonaForge boot-health verification |
| FRR live | Not implemented | Not implemented | Not implemented |
| Active metadata | `/run/personaforge/active.json` remains host-local across container restart | Retained and re-read by status | `/var/lib/personaforge/active.json` is used only after explicit verified persistence |
| Pending transaction | Not implemented | Not implemented | Not implemented |
| Non-persistent persona | Remains represented while live ConfigDB and `/run` remain | Current live rows are rendered for the boot | Saved baseline returns and transient `/run` metadata is cleared by reboot |

## 5. Native SONiC CLI design

### 5.1 Implemented command mapping

| Native command | Core call | Mutation |
|---|---|---:|
| `show personaforge plan <profile> [--json]` | `common.load_plan()` and runtime contracts | No |
| `show personaforge status [--detail] [--json]` | Metadata plus live/saved drift calculation | No |
| `show personaforge drift [--json]` | `calculate_drift()` | No |
| `config personaforge apply <profile> [--allow-disruptive] [--persist] [-y]` | CLI orchestration plus runtime contracts | Yes |
| `config personaforge persist [-y]` | Save, saved-file verification, durable metadata | Yes |
| `config personaforge deactivate [--allow-disruptive] [--persist] [-y]` | Inverse captured actions and optional save | Yes |

`--json` renders the command's structured JSON document. Default output uses compact tables and reasons. `-y` skips interactive confirmation only; it does not grant disruption, reboot, or persistence permission.

`inventory`, `report`, `footprint`, transaction-ID `rollback`, and footprint capture commands are planned but not implemented. `deactivate` is a bounded restoration of captured fields and is not the planned transaction rollback facility.

### 5.2 `sonic-utilities` integration

In the pinned `sonic-utilities` repository:

~~~text
config/personaforge.py
show/personaforge.py
utilities_common/personaforge.py
~~~

`config/main.py` imports the module and registers its Click group with `config.add_command(...)`; `show/main.py` does the same with `cli.add_command(...)`. The implementation follows existing direct command-module patterns rather than platform-specific plugins.

The current modules perform option validation, confirmation, plan loading, rendering, validated writes, restart/save orchestration, verification, and error-to-exit mapping. Moving orchestration behind a stable core API and delayed-import isolation are future refactoring targets.

Source-level CLI registration and behavior tests live in `src/personaforge/tests/test_cli_surface.py` and `test_cli_commands.py`. Built-image command and target-platform tests remain pending.

## 6. Build design

### 6.1 Public entry and Make integration point

~~~bash
make configure PLATFORM=<sonic-platform>
make PERSONAFORGE_PROFILE=l3-bgp-leaf-no-lag <platform-image-target>
# Broadcom example when supported by the selected SONiC tree:
make configure PLATFORM=broadcom
make PERSONAFORGE_PROFILE=l3-bgp-leaf-no-lag target/sonic-broadcom.bin
# Additional personas use the same normal platform target:
make PERSONAFORGE_PROFILE=l3-bgp-bfd-leaf target/sonic-broadcom.bin
make PERSONAFORGE_PROFILE=l3-multirouting-lab target/sonic-broadcom.bin
make PERSONAFORGE_PROFILE=l3-bgp-observability target/sonic-broadcom.bin
~~~

PersonaForge imposes no platform allowlist; `<sonic-platform>` and `<platform-image-target>` are the normal values already supported by the SONiC build tree. Each command is a separate image selection and must be built/tested separately. In particular, the observability build retains artifacts that the reduced profiles omit, while the multi-routing selection changes optional service packaging but retains the shared FRR package containing its child daemons.

The top-level `Makefile` continues its normal dispatch to `Makefile.work`; the command-line variable propagates through GNU Make. PersonaForge integration is in `Makefile.work` immediately after:

~~~make
include rules/config
-include rules/config.user
include rules/personaforge.mk
~~~

This order is required because verified persona-managed defaults include both `?=` and unconditional `=` assignments. `rules/personaforge.mk` is inert when the knob is empty.

When set, it validates the profile name, resolves only `personaforge/profiles/<name>.yaml`, obtains a content-derived build key, and includes the generated fragment. GNU Make included-file remake/restart semantics (or a functionally equivalent prerequisite) create the fragment before downstream component rules are evaluated.

Persona-managed variables are authoritative for the selected profile. If a command-line or `rules/config.user` value explicitly conflicts, Make fails with the variable, requested value, and profile value. The integration must not silently choose one. Unrelated build variables retain normal precedence.

### 6.2 Generation flow

~~~text
profile manifest + schema + catalog + generator + current source commit + selected platform
                                 |
                                 v
                    scripts/personaforge-build
                                 |
                 +---------------+----------------+
                 v                                v
       generated personaforge.mk          normalized plan/evidence
                 |
                 v
       existing component Make rules
                 |
                 v
       normal platform image target
~~~

The helper currently has two internal operations: calculate/validate input identity and generate the build plan/fragment. It is called by Make; users do not run a preprocessing step. Post-build artifact verification remains a separate pending operation.

The fragment contains only catalog-declared assignments, for example:

~~~make
INCLUDE_SNMP = n
INCLUDE_SFLOW = n
INCLUDE_TEAMD = n
BUILD_REDUCE_IMAGE_SIZE = y
~~~

It does not contain shell functions, includes, recipes, `override`, or variables supplied by the manifest. The generator performs atomic writes and escapes/validates all output as Make data.

### 6.3 Build identity, paths, and cache correctness

Use build-key-specific paths so parallel profiles cannot share a mutable fragment:

~~~text
target/personaforge/generated/<profile>/<build-key>/
  personaforge.mk
  input.json
  manifest.normalized.json
  catalog.json
  build-plan.json
~~~

The implemented build key hashes the canonical manifest digest, catalog digest, generator-file digest, selected source commit, platform, and sorted generated settings. The profile name is represented through the manifest identity and output path. Complete submodule identity and discovered build inventory are not separate key fields in this slice. A changed implemented input selects/regenerates the correct fragment; full no-clean profile-switch/image-cache qualification remains pending.

The canonical SONiC image stays at its normal target path. Evidence records that path and digest; CI may publish an additional profile-labeled link/copy.

### 6.4 Build persistence boundary

`PERSONAFORGE_PROFILE` is evaluated only while building the image. The generated fragment feeds existing SONiC component rules, so omitted packages/containers and retained runtime packages become properties of the resulting installer. Once installed, that image composition naturally survives container, Docker, and node restarts; no ConfigDB save or PersonaForge metadata is required to retain build-time omission.

The runtime wheel, schema/catalog, and named profiles are packaged into the image so native commands remain available after boot. Runtime administrative choices are deliberately separate: live `FEATURE` and `FRR_DAEMON` rows survive relevant container restarts while ConfigDB remains live, and only the verified native save flow makes them durable across a cold node reboot. A runtime command cannot add a component omitted from the installed image.

### 6.5 Target artifact verification — pending

The following qualification flow is required but has not yet been executed by an implemented artifact verifier:

1. static inspection of installer, Docker, and package inventories;
2. proof that each requested catalog-mapped artifact is absent and required components remain present;
3. exact installer byte count and digest;
4. boot of the image using the same topology/configuration as B0;
5. BGP L3, database, swss, syncd, route/FPM, and management smoke checks;
6. booted Docker repository/image-ID inventory and shared/unique storage capture;
7. B1 memory sampling under the same workload used for B0/R1/R2.

Build mode does not claim removal of shared orchagent code or individual FRR binaries without a separately implemented and cataloged build control.

## 7. Target evidence and reporting design — pending

No footprint collector or report generator is implemented in the current slice. This section defines the later qualification design and must not be read as collected evidence.

### 7.1 Checkpoints

| ID | State |
|---|---|
| B0 | Standard image baseline |
| R1 | B0 image with selected optional containers disabled |
| R2 | B0 image with R1 plus one unused running optional FRR daemon disabled |
| B1 | Persona-built image from the same source/manifest |

B0/R1/R2 use the exact same installed image. Runtime apply never prunes images. The qualification setup first proves that the R1 container and R2 allowlisted daemon are running and dependency-free; an already stopped process is not a saving. Each checkpoint stores environment identity, topology/configuration digest, workload, stabilization time, sampling timestamps, and raw observations.

### 7.2 Collection contract

Collect at least five steady-state samples per checkpoint:

- host `MemAvailable`;
- per-container cgroup memory from `docker stats --no-stream`;
- running container/process counts;
- BGP-container memory;
- target FRR daemon RSS/PSS from `/proc/<pid>/smaps_rollup` when available.

Collect image/storage evidence using equivalent structured output from:

~~~bash
docker images --digests --no-trunc --format "{{.Repository}}|{{.Tag}}|{{.Digest}}|{{.ID}}|{{.Size}}"
docker system df -v
docker info --format "{{.DockerRootDir}}"
du -x -B1 -s <DockerRootDir>
stat -c "%s" <sonic-installer-artifact>
~~~

Do not sum displayed image sizes because shared layers are repeated. Physical storage claims use Docker shared/unique data, quiescent Docker-root usage, and exact installer bytes. Host, container, and daemon memory are separate views; daemon memory is not added to container memory.

### 7.3 Report schema

The versioned JSON report contains identity/digests, requested and resolved decisions, ordered actions/settings, before/after observations, activation, verification, persistence/rollback, raw samples, aggregates, Docker inventory/storage, artifact evidence, and redaction/schema version. Human-readable output is derived from this JSON.

## 8. Code integration and packaging

| Area | Repository location | Status and deliverable |
|---|---|---|
| Core package | `src/personaforge/` | Implemented manifest/catalog/build/runtime contracts and tests |
| Named profiles and docs | `personaforge/` | Implemented profiles, HLD, Requirements, and manual guide |
| Build integration | `rules/personaforge.mk`, `scripts/personaforge-build`, `Makefile.work` | Implemented Make knob, deterministic generation, identity, and conflict guards; artifact verifier pending |
| Runtime packaging | `src/personaforge/setup.py`, `rules/sonic-utilities.mk` | Implemented wheel plus installed schema/catalog/profiles dependency |
| Native CLI | `src/sonic-utilities/config/personaforge.py`, `show/personaforge.py`, `utilities_common/personaforge.py` | Implemented native commands and shared SONiC helpers |
| YANG | `src/sonic-yang-models/yang-models/sonic-frr-daemon.yang` | Implemented ConfigDB schema |
| BGP templates | `dockers/docker-fpm-frr/frr/supervisord/` | Implemented supervisor and critical-process gating |
| Classic BFD owner | `src/sonic-bgpcfgd/` | Implemented BFD manager/direct-spawn guard |
| Management-framework owner | `src/sonic-frr-mgmt-framework/` | Implemented optional VTY-client filtering |
| FRR live control | No delivered source change | Optional future proof of concept; upstream FRR gitlink remains unchanged |
| Controller/reconciler | Not present | Future ConfigDB/lifecycle subscriptions and recovery |
| Boot recovery | Not present | Future pending/LKG state machine and bounded boot verification |

The exact owning files for restart persistence are:

- `src/sonic-utilities/config/personaforge.py`, `show/personaforge.py`, and `utilities_common/personaforge.py` for the native facade, validated writes, BGP restart, save, and verification helpers;
- existing `featured` behavior for downstream consumption of `FEATURE` intent; PersonaForge does not modify or fully verify that lifecycle in this slice;
- `files/image_config/config-setup/config-setup` and `files/build_templates/per_namespace/bgp.service.j2` for ConfigDB/BGP boot ordering;
- `dockers/docker-fpm-frr/docker_init.sh`, `dockers/docker-fpm-frr/frr/supervisord/supervisord.conf.j2`, and `critical_processes.j2` for BGP restart regeneration;
- `src/sonic-yang-models/yang-models/sonic-frr-daemon.yang` and its `setup.py` packaging entry for schema validation;
- `src/sonic-frr-mgmt-framework/frrcfgd/frrcfgd.py` and `src/sonic-bgpcfgd/bgpcfgd/managers_bfd.py` plus its construction path in `bgpcfgd/main.py` for configuration-owner guards;
- no `src/sonic-frr` source change; FRR-native live control remains optional future work.

Submodule changes are developed and reviewed in their owning Dell mirrors, then pinned by the PersonaForge `sonic-buildimage` integration branch. A build is qualified only against the recorded complete superproject/submodule identity.

New Python dependencies require license/build review and measured image-size impact. Runtime planning and apply require no network access. All names and controls are schema/catalog allowlisted; commands use argv arrays; persisted files are protected; reports redact secrets.

## 9. Verification and implementation ownership

### 9.1 Test layers

The committed source-level suite contains 46 tests covering schema/catalog contracts, all four profiles, unrestricted platform and source-commit selection with identity separation, deterministic build generation and conflicts, CLI registration/behavior, persistence/drift/deactivation, Jinja predicates, `frrcfgd`, `bgpcfgd`, YANG packaging, and the required `FRR_DAEMON` sample ConfigDB fixture. `git diff --check` also passes. A full SONiC platform image build and hardware restart/reboot qualification have not been run.

The table below is the remaining complete qualification target, not a claim of current coverage:

| Layer | Required coverage |
|---|---|
| Unit | Schema, canonical digest, catalog, probes, dependency closure, conflicts, plan ordering, adapters, rollback, report |
| Component | YANG, Jinja predicates, `frrcfgd`, `bgpcfgd` BFD guard, optional `watchfrr` state machine |
| Native CLI | Registration/help, privilege/policy, JSON/text, no-mutation, error statuses, injection safety |
| SONiC target platform | Feature convergence, idempotency, transaction failure injection, BGP restart/recovery, persistence/reboot |
| Build | Empty knob, valid/invalid/conflicting profile, Make include order/restart, profile switching, stale-cache prevention |
| Artifact/boot | Omission proof, required-content proof, image boot, BGP L3 and route/FPM smoke tests |
| Evidence | Controlled B0/R1/R2/B1 collection, raw sample preservation, no double counting |

Current tests live in `src/personaforge/tests/`, including source-level CLI, Jinja, configuration-owner, and YANG contract tests. Future native-repository component tests may be added under their owning repositories, and platform-specific reboot/restart scenarios belong in a PersonaForge test module under the SONiC management test repository when that dependency is added.

Required failure-injection seams are adapter command-runner results/timeouts, ConfigDB write/save failure, controller termination after each transaction transition, BGP restart failure, missing optional and required supervisor processes, adjacency/route/FPM timeout, corrupted/missing pending or LKG record, power loss between durable transitions, boot-verifier timeout, rollback restart failure, ConfigDB reload drift, and stale/mismatched active metadata. Tests must also snapshot Docker image IDs before and after every runtime restart/reboot scenario.

### 9.2 Work packages

| Owner package | Scope | Required dependencies |
|---|---|---|
| PF-Contract | Schema, typed models, digest, catalog validator, fixtures | Requirements Section 4 |
| PF-Inventory | Runtime/build probes and evidence | Catalog probe definitions |
| PF-Resolver | Dependency graph, decisions, plan, activation selection | Contract and inventory |
| PF-Runtime | Lock, state machine, persistence, rollback, runner | Plan/action contracts |
| PF-Feature | Feature and specialized adapters | Runtime and inventory |
| PF-FRR | Restart path and optional live path | Runtime, prototype, FRR review |
| PF-CLI | Core facade, native command groups, packaging | Contract, resolver, runtime, evidence |
| PF-Build | Make integration, generator, identity/cache, verifier | Contract, resolver, source inventory |
| PF-Evidence | Report schema, collectors, comparison | Inventory and transaction records |
| PF-Validation | Platform build/boot, failure injection, footprint qualification | Applicable packages above |

Versioned contract fixtures are shared so packages can be developed independently. Merge order follows interface dependencies, not product stages.

Dependency-ordered implementation plan:

1. **PF-Contract — implemented:** strict Persona v1alpha1 loader/schema/model/digest, catalog schema/validator, 202605 catalog, four profiles, and positive/negative tests.
2. **PF-Inventory — partial:** live `FEATURE`/`FRR_DAEMON` table reads and pinned build inputs are implemented; routing-mode, dependency, system, and operational probes are pending.
3. **PF-Resolver — partial:** deterministic catalog-mapped runtime actions and build settings are implemented; complete dependency graph/evidence and activation selection are pending.
4. **FRR startup contract — implemented source slice:** YANG model, BGP Jinja predicates, `frrcfgd` filtering, classic `bgpcfgd` guard, and source-level tests are implemented; platform image/hardware qualification is pending.
5. **PF-Runtime and PF-Feature — partial:** current/durable active metadata, ConfigDB equality verification, persistence, drift, idempotency, and deactivation are implemented; transaction journal, full adapter verification, and automatic rollback are pending.
6. **PF-FRR restart path — partial:** candidate rows, explicit authorization, BGP restart, service-active check, and ConfigDB verification are implemented; routing convergence, rollback restart, and failure injection are pending.
7. **Boot recovery — pending:** pending/LKG state, systemd boot verifier, bounded recovery, and reboot tests are not implemented; warm reboot remains unsupported.
8. **PF-CLI and packaging — partial:** native implemented commands and wheel dependency are present; unified API, planned commands, built-image tests, and target-platform qualification are pending.
9. **PF-Build and PF-Evidence — partial:** Make integration and deterministic artifacts are implemented; post-build artifact verification, B0/R1/R2/B1 collection, boot/smoke qualification, and measured claims are pending.

### 9.3 Definition of done

The current hackathon slice is implemented but the full product design is complete only when Requirements Section 11 passes and:

- every action has a named owner adapter, timeout, postcondition, and rollback/build proof;
- all native commands are exercised from a built SONiC image;
- the unset Make knob preserves the standard selection path;
- valid/invalid/conflicting profile and profile-switch tests pass without stale values;
- B0/R1/R2 prove runtime memory effects with unchanged image inventory;
- B1 proves requested artifact absence, boot health, and measured storage difference;
- all evidence identifies the exact manifest, catalog, source, submodules, platform, and image.

### 9.4 Requirement traceability

| Requirement group | Implementing HLD sections |
|---|---|
| PF-MAN | 3.1–3.3 |
| PF-INV | 3.2–3.3 |
| PF-RES, PF-PLN | 3.2–3.3 |
| PF-FEA | 4.2–4.3 |
| PF-FRR | 4.4–4.5 |
| PF-TXN | 4.1–4.2 and 4.6 |
| PF-CLI | 3.4 and 5 |
| PF-BLD | 6 |
| PF-RPT | 7 |
| PF-SEC, PF-NFR | 3.4, 4.2, 4.6, 5.2, 8, and 9 |
