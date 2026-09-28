# PersonaForge Requirements Specification

> **Project:** SONiC OCP Hackathon 2026 — PersonaForge
> **Target:** Community SONiC `sonic-buildimage` `202605`
> **Status:** Implementation specification
> **Normative terms:** MUST, SHOULD, and MAY
> **Design:** [PersonaForge High-Level Design](PersonaForge-HLD.md)

---

## 1. Purpose and product outcome

PersonaForge converts one declarative persona into either:

- a **runtime plan** that disables supported, unused containers and FRR daemons in an already installed image; or
- a **build plan** that omits supported optional artifacts while building the normal SONiC platform image target.

Both modes use the same manifest, release catalog, dependency resolver, and evidence format. Runtime mode primarily demonstrates steady-state memory reduction. Build mode demonstrates image-content and storage reduction and may also reduce booted memory. Runtime mode does not claim to remove Docker images or reduce installer size.

The runtime engine and native `config personaforge` and `show personaforge` commands MUST be installed in the SONiC image. Build selection MUST be integrated into `sonic-buildimage` through `PERSONAFORGE_PROFILE`; neither mode requires an external PersonaForge service.

The primary hackathon persona is `l3-bgp-leaf-no-lag`: a SONiC BGP leaf that retains L3 forwarding, BGP, SSH/CLI, and required platform services while requesting omission or runtime deactivation of unused optional functions. The persona contract does not restrict the selected SONiC platform or ASIC count.

Three additional demonstration personas are required: `l3-bgp-bfd-leaf` exercises affirmative BFD/LLDP enablement, `l3-multirouting-lab` exercises management-framework FRR daemon gating, and `l3-bgp-observability` retains and enables common discovery/observability services. Their exact contracts and acceptance outcomes are defined in Section 4.2.1.

## 2. Baseline, scope, and boundaries

### 2.1 Baseline

- Development and evidence MUST use an immutable commit selected from community `sonic-buildimage/202605`, including the exact submodule revisions pinned by that commit.
- The SONiC source baseline reviewed on 2026-09-28 is `sonic-buildimage` `03a90ea321b3d9f71ae88ae23d4ccd146225e95c`, matching the Dell mirror's `202605` ref. Delivery is on `rathnasabapathyv/2026_hackathon_persona`; the commit containing this document is the implementation identity.
- The baseline `sonic-utilities` revision is `bf72b0aead74519e4a2c973902fa2f844929eac2`; the PersonaForge CLI revision is `be94ea1332c37f726504f4da7522e2a30c43abd7` on its matching delivery branch.
- The delivered superproject continues to pin upstream FRR `4cb6d9e6bfe4ad503d1fab21e6f665804b0649ac`; PersonaForge makes no upstream FRR source change.
- Plans, transactions, builds, and reports MUST record the source commit and catalog digest.
- Persona manifests and the release catalog MUST NOT maintain a platform or ASIC-count allowlist. The selected build platform remains recorded in build identity and evidence, while functional qualification is performed on each target using its normal SONiC build support.
- New FRR daemon controls require an image containing the new YANG model and consumers. Restarting BGP or rebooting an unchanged image cannot add missing code.

This specification is the complete normative target. The delivered persistence-focused slice implements the platform-independent contract/schema, bounded runtime and build planners, Make integration, four profiles, YANG and FRR startup consumers, native plan/apply/persist/deactivate/status/drift commands, ConfigDB/BGP-service verification, and 45 source-level tests. Dependency-probe execution, operational/routing-mode inventory, full convergence verification, transaction rollback, controller/boot recovery, artifact verification, footprint reporting, and target-platform qualification remain requirements for later work.

### 2.2 In scope

- strict persona schema, normalization, and digest;
- release catalog, target/build inventory, dependency resolution, and no-mutation planning;
- SONiC `FEATURE` lifecycle through a typed adapter;
- bounded FRR daemon administrative state for `bfdd`, `ospfd`, `pimd`, and `pathd`;
- BGP-container restart activation, with authorized node reboot as a last resort;
- an FRR-native live-control proof of concept when feasible;
- transactional apply, verification, persistence, rollback, drift/status, and evidence;
- native SONiC `config` and `show` commands;
- Make-integrated persona image builds and artifact verification;
- repeatable memory and Docker/image-storage comparison.

### 2.3 Out of scope

- arbitrary process killing or generic systemd/supervisor control;
- runtime unloading of SWSS/orchagent classes;
- dynamic removal of YANG models or CLI commands;
- removal of individual FRR binaries from the FRR package;
- disabling protected routing, database, forwarding, configuration-owner, or supervisor processes;
- a claim that every platform or multi-ASIC topology is functionally qualified merely because the generic persona contract no longer blocks it;
- automatic support for every warm-restart or upgrade path;
- preservation of a PersonaForge transaction or active-persona record across an image upgrade; the new image must be inventoried and the persona revalidated/reapplied explicitly;
- a promised percentage saving before measurement;
- image pruning as part of runtime apply.

## 3. Shared functional model

~~~text
persona + release catalog + inventory
                  |
                  v
       validate and resolve dependencies
                  |
                  v
          immutable ordered plan
             /             \
            v               v
 runtime transaction     Make build integration
            \               /
             v             v
             status and evidence
~~~

Every component decision MUST have one of these states:

| State | Meaning |
|---|---|
| `retained` | Required, protected, or blocked by a dependency. |
| `enabled` | Present and explicitly requested active. |
| `disabled` | Present and administratively inactive at runtime. |
| `omitted` | Excluded from a persona build through a verified build control. |
| `default` | PersonaForge makes no state change. |
| `absent` | Not present in the installed image or selected build inventory. |
| `blocked` | A valid control exists, but dependency or policy prevents the action. |
| `unsupported` | The target/catalog has no qualified control for the request. |

`absent`, `disabled`, and `omitted` are different outcomes and MUST NOT be reported interchangeably.

## 4. Persona manifest

### 4.1 Normative manifest requirements

| ID | Priority | Requirement |
|---|---|---|
| PF-MAN-001 | MUST | The manifest shall use the supported `apiVersion` and `kind`. |
| PF-MAN-002 | MUST | Unknown fields, duplicate keys, custom YAML tags, invalid types, and invalid enums shall be rejected. |
| PF-MAN-003 | MUST | Intent shall be expressed as capabilities and bounded overrides, never commands or executable content. |
| PF-MAN-004 | MUST | Compatibility shall identify the SONiC release. Platform and ASIC-count restrictions shall not be encoded in a persona or release catalog. |
| PF-MAN-005 | MUST | Policy shall distinguish ordinary, disruptive, and reboot-authorized execution. |
| PF-MAN-006 | MUST | Runtime persistence shall be explicit. |
| PF-MAN-007 | MUST | Overrides shall be checked against the catalog, required capabilities, and actual inventory. |
| PF-MAN-008 | SHOULD | Metadata shall identify the persona description and owner. |
| PF-MAN-009 | MUST | Canonical normalization and SHA-256 shall identify the exact manifest used by a plan, transaction, build, or report. |
| PF-MAN-010 | MUST | A capability shall not occur in both `require` and `omit`. |
| PF-MAN-011 | MUST | An override shall not defeat a required capability, protected component, configured dependency, or compatibility constraint. |
| PF-MAN-012 | MUST | All policy keys shall be explicit; corresponding CLI authorization is additionally required for disruptive, reboot, and persistence operations. |
| PF-MAN-013 | MUST | Every shipped named persona shall validate against the pinned catalog, have a filename matching `metadata.name`, and produce a distinct deterministic manifest digest and build key when its normalized intent differs. |
| PF-MAN-014 | MUST | Demo persona documentation shall distinguish component lifecycle intent from protocol configuration; enabling an FRR daemon shall not imply that protocol neighbors, sessions, rendezvous points, policies, or peers are configured. |

### 4.2 Reference manifest

~~~yaml
apiVersion: personaforge.sonic.net/v1alpha1
kind: Persona

metadata:
  name: l3-bgp-leaf-no-lag
  description: Lab leaf using BGP and host SSH/CLI
  owner: dell-sonic-ocp-2026

compatibility:
  sonicRelease: "202605"

capabilities:
  require:
    - l3-forwarding
    - bgp
    - ssh-cli
    - platform-monitoring
  omit:
    - link-aggregation
    - dhcp-relay
    - nat
    - macsec
    - mux
    - sflow
    - snmp
    - gnmi
    - telemetry
    - restapi

overrides:
  features:
    lldp: disabled
  frrDaemons:
    bfdd: disabled

policy:
  failOnConfiguredDependency: true
  allowDisruptive: true
  allowNodeReboot: false
  persistRuntime: true

build:
  reduceFilesystem: false
~~~

#### 4.2.1 Additional demo persona requirements

The following additional profiles are version-controlled contract fixtures and demo inputs. Each MUST satisfy the common `202605` release constraint without a platform or ASIC-count allowlist. Each MUST set `failOnConfiguredDependency: true`, `allowDisruptive: true`, `allowNodeReboot: false`, and `persistRuntime: true`. Runtime persistence still requires an explicit CLI `--persist` or `config personaforge persist`; these manifest values do not cause an automatic save.

| Profile | Required capabilities | Omitted capabilities | Explicit feature/FRR intent | Build intent | Required demonstration |
|---|---|---|---|---|---|
| `l3-bgp-bfd-leaf` | `l3-forwarding`, `bgp`, `bfd`, `ssh-cli`, `platform-monitoring` | DHCP relay, NAT, MACsec, MUX, sFlow, SNMP, gNMI, telemetry, REST API | LLDP `enabled`; `bfdd` `enabled` | Standard ONIE-compatible filesystem mode; retain LLDP and default link aggregation; omit catalog-controlled unused services | Plan shows BFD enable intent; apply with disruption authorization restarts BGP; `bfdd` is expected by supervisor and active; persistence survives BGP restart and cold reboot |
| `l3-multirouting-lab` | `l3-forwarding`, `bgp`, `ssh-cli`, `platform-monitoring` | Link aggregation, DHCP relay, NAT, MACsec, MUX, sFlow, SNMP, gNMI, telemetry, REST API | LLDP and `bfdd` `disabled`; `ospfd`, `pimd`, and `pathd` `enabled` | Standard ONIE-compatible filesystem mode and omission of catalog-controlled optional services; no individual FRR binary removal | On a management-framework image, supervisor/critical lists and `frrcfgd` reflect all four daemon states; no claim is made that protocol configuration or convergence is created by the persona |
| `l3-bgp-observability` | `l3-forwarding`, `bgp`, `ssh-cli`, `platform-monitoring`, `lldp`, `sflow`, `snmp`, `gnmi`, `telemetry` | Link aggregation, DHCP relay, NAT, MACsec, MUX, REST API | LLDP, sFlow, SNMP, gNMI, and telemetry `enabled`; `bfdd` `disabled` | Standard ONIE-compatible filesystem mode; retain observability artifacts; omit unrelated catalog-controlled services | Plan and build artifacts retain/enable observability services, BFD remains disabled, and persistence restores the desired rows after restart/reboot |

The following constraints are normative for these demonstrations:

- `l3-bgp-bfd-leaf` supports both classic and management-framework routing modes only for the catalog-qualified `bfdd` control. BFD sessions and consumers are configured separately through normal SONiC interfaces.
- `l3-multirouting-lab` MUST be rejected or reported unsupported outside management-framework routing mode for `ospfd`, `pimd`, and `pathd` activation. The persona controls daemon administrative lifecycle only.
- `l3-bgp-observability` MUST NOT fabricate a missing `FEATURE` row. Runtime enable actions apply only to features retained in the installed image; its own persona build retains the catalog-controlled observability artifacts.
- A different persona MUST NOT be applied over an active persona. The operator MUST deactivate the current persona first so captured prior values remain unambiguous.

### 4.3 Keyword reference

No fields other than those listed below are valid in `v1alpha1`.

| Path | Type | Required/default | Purpose and validation |
|---|---|---|---|
| `apiVersion` | String enum | Required | Exactly `personaforge.sonic.net/v1alpha1`; unsupported versions are rejected. |
| `kind` | String enum | Required | Exactly `Persona`. |
| `metadata.name` | String | Required | Persona identity; must match `[a-z0-9]([-a-z0-9]*[a-z0-9])?` and be at most 63 characters. |
| `metadata.description` | String | Optional | Review text only; no execution semantics. |
| `metadata.owner` | String | Optional | Ownership text only; does not grant authorization. |
| `compatibility.sonicRelease` | Quoted string | Required | Exact release catalog, initially `"202605"`. This is the only compatibility restriction in `v1alpha1`. |
| `capabilities.require` | Non-empty unique name list | Required | Functions that must remain available. |
| `capabilities.omit` | Unique name list | `[]` | Functions requested inactive at runtime or absent from a build. |
| `overrides.features.<name>` | State enum | Optional | `default`, `enabled`, or `disabled` for a catalog-known SONiC feature. |
| `overrides.frrDaemons.<name>` | State enum | Optional | `default`, `enabled`, or `disabled` for an allowlisted optional FRR daemon. |
| `policy.failOnConfiguredDependency` | Boolean | Required | Must be `true` for apply; `false` is diagnostic-plan only and never authorizes a conflicting action. |
| `policy.allowDisruptive` | Boolean | Required | Makes catalog-classified disruptive actions eligible; the apply command must also opt in. |
| `policy.allowNodeReboot` | Boolean | Required | Makes node reboot eligible only when disruptive action is also authorized and the CLI opts in. |
| `policy.persistRuntime` | Boolean | Required | Requests persistence only after successful verification; the apply command must also opt in. |
| `build.reduceFilesystem` | Boolean | `false` | Requests `BUILD_REDUCE_IMAGE_SIZE=y` only for a baseline/platform combination qualified for SONiC's slim-image archive and boot path. Platform-independent profiles keep this false. |

For a named build profile, the file MUST be `personaforge/profiles/<metadata.name>.yaml`; the filename, `metadata.name`, and `PERSONAFORGE_PROFILE` value MUST match.

### 4.4 Capability semantics

`require` expands to a transitive protected component set. If the target cannot provide a required capability, planning fails.

`omit` is an optimization request, not force permission. Resolution may produce `omitted`, `disabled`, `absent`, `blocked`, or `unsupported`. A component shared with a required capability is retained.

The initial catalog vocabulary is:

| Capability | Dependency or protection intent |
|---|---|
| `l3-forwarding` | Protect database, swss/orchagent, syncd, and required host/network services. |
| `bgp` | Protect the BGP container, `bgpd`, `zebra`, `staticd`, FPM path, and configuration owner. |
| `ssh-cli` | Protect the retained operator management path. |
| `platform-monitoring` | Protect required pmon/platform services; exact behavior is provided by the selected SONiC platform. |
| `link-aggregation` | Retain teamd when `PORTCHANNEL` or `PORTCHANNEL_MEMBER` is configured. |
| `bfd` | Retain `bfdd` when BFD configuration, sessions, or consumers exist. |
| `dhcp-relay` | Retain relay components when relay configuration exists. |
| `nat` | Retain NAT when enabled or NAT tables are populated. |
| `macsec` | Retain MACsec when any port references a MACsec profile. |
| `mux` | Retain MUX for DualToR metadata or `MUX_CABLE` configuration. |
| `sflow` | Retain sFlow when collectors or sessions exist. |
| `snmp`, `gnmi`, `telemetry`, `restapi` | Retain when required as a management/telemetry path or by protected configuration. |
| `lldp` | Retain or disable according to intent and discovered dependencies. |

The catalog, not the manifest, maps capabilities to release-specific features, packages, daemons, build variables, and probes.

### 4.5 Override semantics

- `default` causes no PersonaForge state mutation and preserves image/platform behavior.
- A feature override uses an actual catalog-known `FEATURE` key. PersonaForge never derives an `INCLUDE_*` variable from a feature name.
- Enabling an absent feature fails. Disabling an absent optional feature is an `absent` no-op.
- Immutable, core, required, or configured features cannot be disabled.
- The initial FRR daemon allowlist is `bfdd`, `ospfd`, `pimd`, and `pathd`.
- `bgpd`, `zebra`, `staticd`, `fpmsyncd`, `mgmtd`, configuration daemons, `watchfrr`, and supervisors are not valid override keys.
- Enabling an FRR daemon requires a supported configuration owner for the active routing mode. Disabling it requires no protocol configuration, sessions, or known consumers.
- FRR daemon overrides affect runtime/startup intent; `v1alpha1` does not remove individual FRR binaries from a build.

### 4.6 Resolution, normalization, and conflicts

Resolution order is fixed:

1. safely parse and validate structure;
2. apply documented defaults and canonicalize names/lists/maps;
3. select and validate the exact release catalog; platform and ASIC topology are recorded observations, not compatibility gates;
4. expand required capabilities and protect their dependency closure;
5. map omitted capabilities to candidates;
6. apply non-conflicting overrides;
7. evaluate target/build inventory and configured-dependency probes;
8. select policy-authorized activation methods;
9. emit an ordered immutable plan and independent manifest, catalog, and inventory/source digests.

There is no last-writer-wins behavior. Conflicts such as required BFD with `bfdd: disabled`, configured PortChannels with `link-aggregation` omitted, or a required feature with a disabling override fail with a dependency trace.

Canonical JSON is produced by applying defaults, sorting map keys, treating capability lists as unique sorted sets, and retaining all meaningful metadata and policy. The manifest SHA-256 is calculated over those canonical bytes.

## 5. Common inventory, resolution, and planning requirements

### 5.1 Inventory

| ID | Priority | Requirement |
|---|---|---|
| PF-INV-001 | MUST | Inventory shall record SONiC version/image, source identity when available, platform, ASIC count, and routing configuration mode. |
| PF-INV-002 | MUST | Runtime inventory shall read available/mutable `FEATURE` entries and their current state. |
| PF-INV-003 | MUST | Runtime inventory shall capture relevant systemd units, containers, supervisor programs, and FRR processes. |
| PF-INV-004 | MUST | Inventory shall execute catalog-declared ConfigDB dependency probes. |
| PF-INV-005 | MUST | Inventory shall detect `FRR_DAEMON` schema/consumer support and qualified activation methods. |
| PF-INV-006 | MUST | Mutation/build generation shall reject an incompatible release or catalog and a malformed source identity. It shall record the current source commit but shall not require it to equal a self-referential catalog hash or reject a supported SONiC build because of a PersonaForge platform or ASIC-count allowlist. |
| PF-INV-007 | MUST | An unknown or failed probe shall fail closed for destructive/disruptive action and identify its source. |
| PF-INV-008 | SHOULD | Plan-only output may describe an incompatible target without authorizing mutation. |

### 5.2 Catalog and resolver

| ID | Priority | Requirement |
|---|---|---|
| PF-RES-001 | MUST | A versioned `202605` catalog shall map capabilities to components, probes, controls, risks, and verification. |
| PF-RES-002 | MUST | Resolution shall compute transitive requirements, conflicts, and protected components. |
| PF-RES-003 | MUST | Identical manifest, catalog, and inventory inputs shall produce an identical ordered plan. |
| PF-RES-004 | MUST | Database, swss, syncd, and routing/FPM/configuration processes required by the persona shall be protected. |
| PF-RES-005 | MUST | Link-aggregation omission shall fail while `PORTCHANNEL` or `PORTCHANNEL_MEMBER` configuration exists. |
| PF-RES-006 | MUST | NAT, sFlow, MACsec, MUX, DHCP relay, and management omissions shall use component-specific dependency probes. |
| PF-RES-007 | MUST | FRR daemon disable shall fail while configuration, sessions, or known consumers require it. |
| PF-RES-008 | MUST | A missing component shall be reported `absent`, not `disabled`. |
| PF-RES-009 | MUST | Unsupported in-process optimization shall be reported `unsupported`, never approximated with a process kill. |
| PF-RES-010 | MUST | Every decision shall carry a reason and an inventory/catalog evidence reference. |

### 5.3 Plan

| ID | Priority | Requirement |
|---|---|---|
| PF-PLN-001 | MUST | Planning shall perform no mutation. |
| PF-PLN-002 | MUST | Every action shall identify component, adapter/build control, prior state, desired state, activation, disruption, verification, and rollback or build proof. |
| PF-PLN-003 | MUST | Missing required dependency, control, or activation support shall fail before mutation/build. |
| PF-PLN-004 | MUST | Online-safe, disruptive, and node-reboot actions shall be visibly classified. |
| PF-PLN-005 | MUST | Node reboot shall require both manifest authorization and matching command authorization. |
| PF-PLN-006 | SHOULD | No-op decisions shall remain visible as idempotency evidence. |

## 6. Runtime requirements

### 6.1 Runtime boundaries and feature adapter

Runtime support is not limited to the `FEATURE` table. `FEATURE` controls whole containers; FRR child daemons and lifecycle exceptions use separate typed adapters.

| ID | Priority | Requirement |
|---|---|---|
| PF-FEA-001 | MUST | A present, mutable whole-container feature shall use SONiC `FEATURE` lifecycle semantics. |
| PF-FEA-002 | MUST | The adapter shall verify applicable ConfigDB, STATE_DB, systemd, and container postconditions. |
| PF-FEA-003 | MUST | Immutable, core, and required features shall never be disabled. |
| PF-FEA-004 | MUST | Lifecycle exceptions, including telemetry idle behavior, shall use specialized adapters and truthful status. |
| PF-FEA-005 | MUST | Non-container controls shall use separate typed adapters rather than fabricated `FEATURE` entries. |
| PF-FEA-006 | SHOULD | Existing SONiC APIs/commands shall be reused where they provide the required lifecycle semantics. |

### 6.2 FRR daemon contract and activation

`FRR_DAEMON|<daemon>` in ConfigDB carries `admin_status=default|enabled|disabled`. Missing data and `default` preserve existing behavior.

| ID | Priority | Requirement |
|---|---|---|
| PF-FRR-001 | MUST | `FRR_DAEMON` shall have a SONiC YANG model with bounded daemon and state enums. |
| PF-FRR-002 | MUST | The initial daemon allowlist shall be `bfdd`, `ospfd`, `pimd`, and `pathd`. |
| PF-FRR-003 | MUST | Core routing/FPM/configuration/supervisor processes shall remain protected. |
| PF-FRR-004 | MUST | BGP supervisor programs and critical-process expectations shall use the same desired state. |
| PF-FRR-005 | MUST | `frrcfgd` shall exclude intentionally disabled optional daemons from its VTY connection set. |
| PF-FRR-006 | MUST | Classic `bgpcfgd` BFD management shall not respawn disabled `bfdd`. |
| PF-FRR-007 | MUST | `frr_mgmt_framework_config` shall remain a routing-mode selector, not a persona knob. |
| PF-FRR-008 | MUST | `default_bgp_status` shall not be reused because it controls neighbor state, not `bgpd`. |
| PF-FRR-009 | MUST | Enable shall fail when the routing mode lacks a qualified configuration owner. |
| PF-FRR-010 | MUST | Activation shall be selected from discovered support and authorized policy, not a fixed fallback sequence. |
| PF-FRR-011 | MUST | BGP-restart activation shall write candidate intent, restart only BGP, and verify required processes, BGP adjacency, routes, and FPM recovery. |
| PF-FRR-012 | MUST | Restart failure shall restore prior intent, restart BGP again, and verify rollback recovery. |
| PF-FRR-013 | MUST | Node reboot shall be an explicitly authorized last resort for controls already installed in the image. |
| PF-FRR-014 | MUST | Restart/reboot shall never be described as adding a missing schema, binary, or controller. |
| PF-FRR-015 | SHOULD | FRR `watchfrr` should expose allowlisted live administrative enable/disable and separate administrative/operational state. |
| PF-FRR-016 | SHOULD | Live disable should suppress restart before stop and remove the daemon from readiness/down accounting. |
| PF-FRR-017 | SHOULD | Live enable should report success only after start, connection, and health verification or timeout. |
| PF-FRR-018 | SHOULD | A SONiC adapter should bridge ConfigDB intent to the FRR-owned interface and publish result; FRR shall not depend on Redis. |
| PF-FRR-019 | MUST | Direct `supervisorctl stop` without durable intent and health integration shall remain an experiment, not a supported apply path. |

The supported activation preference is the least disruptive method that is both present and qualified: FRR-native live control when qualified, otherwise BGP restart, otherwise explicitly authorized node reboot. Unqualified methods are not silently selected.

### 6.3 Runtime transaction and persistence

| ID | Priority | Requirement |
|---|---|---|
| PF-TXN-001 | MUST | Apply shall acquire a global PersonaForge transaction lock. |
| PF-TXN-002 | MUST | Apply shall refresh inventory and dependencies immediately before mutation. |
| PF-TXN-003 | MUST | The snapshot shall include every ConfigDB row and relevant operational state that may change. |
| PF-TXN-004 | MUST | Actions shall execute in deterministic dependency order. |
| PF-TXN-005 | MUST | Every action shall have a finite timeout and explicit postcondition. |
| PF-TXN-006 | MUST | Failure shall trigger best-effort reverse-order rollback of completed actions. |
| PF-TXN-007 | MUST | Failed candidates shall not be committed. Reboot staging additionally requires a pending marker, last-known-good snapshot, bounded boot verification, and automatic recovery. |
| PF-TXN-008 | MUST | Successful requested persistence shall save SONiC configuration and active-persona metadata only after verification. |
| PF-TXN-009 | MUST | Reapplying an already converged persona shall succeed as a no-op. |
| PF-TXN-010 | SHOULD | Failed rollback shall record degraded state and actionable recovery guidance. |

The current persistence-focused implementation covers deterministic runtime planning, validated ConfigDB writes, explicit disruption authorization, live post-write verification, native SONiC save, saved-file verification, active metadata, idempotent reapply, drift reporting, and explicit deactivation. The global lock, complete transaction journal, automatic failure rollback, pending reboot state, and boot verifier remain required later work and shall not be inferred from the current CLI.

### 6.4 Restart, reboot, and reconciliation contract

The unmodified 202605 baseline proves that `config save` serializes live ConfigDB to `/etc/sonic/config_db.json`, flushes, and `fsync`s the file; `config reload` YANG-validates input, rejects tables without a model (except the existing `bgpraw` exception), replaces ConfigDB, and normally restarts services. Boot `config-setup` reloads the saved file before BGP because `bgp.service` requires and follows `config-setup.service`. That unmodified baseline did not contain a `FRR_DAEMON` YANG model or template predicate; the current PersonaForge branch adds those consumers and the persistence-focused CLI, but still has no controller, transaction store, rollback engine, or boot verifier. The behaviors below remain the complete normative contract, with the implemented subset stated explicitly in Section 6.3.

| ID | Priority | Requirement |
|---|---|---|
| PF-REC-001 | MUST | ConfigDB shall be the desired-state source for `FEATURE` and `FRR_DAEMON`; STATE_DB shall contain observed convergence/health only and shall not be used to reconstruct intent. |
| PF-REC-002 | MUST | Restart of an optional feature container or its host service shall re-observe the live ConfigDB `FEATURE` row and converge to it through SONiC feature lifecycle ownership; a disabled feature shall remain disabled and status shall show desired and observed state. |
| PF-REC-003 | MUST | Every BGP-container start shall regenerate `supervisord.conf` and `critical_processes` from the same ConfigDB `FRR_DAEMON` predicate before supervisor starts. `frrcfgd` and classic `bgpcfgd` shall honor that predicate. |
| PF-REC-004 | MUST | A qualified FRR live-control adapter shall continuously reconcile from ConfigDB. Loss of live process state or BGP-container restart shall reconstruct the same state from ConfigDB; live state alone is never durable intent. |
| PF-REC-005 | MUST | Restart of the PersonaForge controller shall load active metadata and any nonterminal transaction record, compare ConfigDB and operational state with desired intent, and either resume safe verification/reconciliation or enter a reported degraded state. It shall not repeat an uncertain mutation. |
| PF-REC-006 | MUST | `persistRuntime: true` plus CLI `--persist` shall, after successful live verification, run native `config save -y`, re-read `/etc/sonic/config_db.json` to verify the persona rows were saved, and only then atomically persist `/var/lib/personaforge/active.json`. Either authorization alone is insufficient. |
| PF-REC-007 | MUST | Without authorized persistence, live ConfigDB intent is expected to survive relevant container/controller restarts in the current boot, but a cold node reboot shall restore the last saved ConfigDB baseline and clear/reclassify non-persistent active metadata. |
| PF-REC-008 | MUST | A reboot-activated transaction shall durably store a pending marker, candidate identity, last-known-good ConfigDB rows and active metadata before reboot. A bounded boot verifier shall commit only after health verification; otherwise it shall restore last-known-good, save it, perform at most the catalog-bounded recovery restart/reboot, and report rollback or degraded state. |
| PF-REC-009 | MUST | ConfigDB reload shall be treated as an external desired-state replacement. The controller shall detect persona drift after reload and apply the configured policy: report-only by default, or reconcile only when the active persisted record explicitly authorizes reconciliation and dependencies still pass. |
| PF-REC-010 | MUST | Drift checks shall run after controller start, managed container/BGP restart, ConfigDB reload completion, and boot verification. A failed or unsafe reconciliation shall never be silently forced. |
| PF-REC-011 | MUST | `show personaforge status --detail` after any restart shall report persisted versus current-boot intent, ConfigDB desired state, observed STATE_DB/process state, pending transaction, drift, last verification, and recovery action. |
| PF-REC-012 | MUST | A restart or reboot shall never be offered as remediation for a missing model, binary, package, template consumer, or controller. |

The feasible target behavior is:

| Control type | Selective container restart | BGP restart | Cold node reboot |
|---|---|---|---|
| `FEATURE` state | Source: live ConfigDB. `featured`/SONiC feature lifecycle owns convergence; PersonaForge verifies ConfigDB, STATE_DB, unit, and container. Failure is reported and transaction rollback applies when PersonaForge initiated it. | BGP is itself protected; restarting BGP does not change unrelated `FEATURE` rows. | Only an authorized, verified `config save` makes the changed row durable. Boot `config-setup` loads the saved row and feature lifecycle converges it. |
| FRR restart-activated state | Not applicable to unrelated feature restarts. | Source: live ConfigDB `FRR_DAEMON`. BGP `docker_init.sh`/`sonic-cfggen` must render supervisor and critical lists before `supervisord`; configuration owners must omit disabled clients/spawn paths. Verification covers required daemons, BGP, routes, and FPM; failure restores rows and restarts once for rollback. | Source: saved ConfigDB. `config-setup.service` must complete before `bgp.service`; BGP renders saved intent. Missing schema/consumers is a hard incompatibility, not recovery. |
| FRR live state | Controller re-observes/reconciles only when its owning adapter or relevant process restarts. | Container loss discards live state; startup render restores ConfigDB intent, then the live adapter reattaches and verifies. | Saved intent is rendered at BGP start and the live adapter reconciles after ConfigDB/BGP readiness. |
| Active persona metadata | Non-persistent identity is retained in `/run/personaforge/active.json`; authorized persistent identity is retained in `/var/lib/personaforge/active.json`. Status revalidates either record against ConfigDB. | Unchanged by BGP restart because both paths are host-owned. | `/run` is cleared. `/var/lib` is available only for an explicitly persisted persona and is valid only when it matches the ConfigDB rows restored from the saved file. |
| Pending transaction | Controller detects and resolves a nonterminal record without replaying uncertain writes. | Coordinator completes verification or restores last-known-good and repeats only the bounded rollback restart. | `personaforge-boot-verify.service` resolves pending to committed, rolled back, or degraded after ConfigDB and managed services become ready. |
| Non-persistent persona | Remains current-boot intent while live ConfigDB is intact and is reverified. | Restart templates consume the current live ConfigDB row, so restart-activated state remains for this boot. | Returns to the previously saved ConfigDB baseline; non-persistent active metadata must not be presented as active. |

Warm reboot is not qualified in the initial slice. Until dedicated target-platform tests prove it, PersonaForge shall reject warm-reboot activation and make no survival guarantee beyond the underlying saved ConfigDB behavior.

### 6.5 Native SONiC CLI

The complete required command surface is listed below. The current persistence-focused slice implements `plan`, `status`, `drift`, `apply`, `persist`, and `deactivate`; `inventory`, `report`, `footprint`, transaction-ID `rollback`, and footprint capture remain pending.

| Command | Access | Behavior |
|---|---|---|
| `show personaforge inventory [--json]` | Read-only | Display compatibility, components, dependencies, and supported activation methods. |
| `show personaforge plan <profile> [--json]` | Read-only | Validate and resolve a named installed profile or bounded manifest path without mutation. |
| `show personaforge status [--detail] [--json]` | Read-only | Display active persona, drift, transaction, and FRR administrative/operational state. |
| `show personaforge drift [--json]` | Read-only | Compare active desired state with live ConfigDB. |
| `show personaforge report [<transaction-id>] [--json]` | Read-only | Display transaction and verification evidence. |
| `show personaforge footprint [--checkpoint B0\|R1\|R2\|B1] [--json]` | Read-only | Display stored footprint checkpoints and deltas. |
| `config personaforge apply <profile> [--allow-disruptive] [--allow-node-reboot] [--persist] [-y]` | Root | Execute a final runtime plan; `--allow-node-reboot` and coordinator-based execution are pending in the current slice. |
| `config personaforge persist [-y]` | Root | Save a verified, drift-free active persona through the native SONiC configuration-save path. |
| `config personaforge deactivate [--allow-disruptive] [--persist] [-y]` | Root | Restore the ConfigDB values captured before activation; optionally save deactivation. |
| `config personaforge rollback <transaction-id> [-y]` | Root | Restore and verify an eligible transaction snapshot. |
| `config personaforge footprint capture <B0\|R1\|R2\|B1> [-y]` | Root | Capture evidence without changing persona desired state. |

| ID | Priority | Requirement |
|---|---|---|
| PF-CLI-001 | MUST | The image shall expose the `config personaforge` and `show personaforge` groups above. |
| PF-CLI-002 | MUST | CLI modules shall be thin wrappers over one in-image API and contain no resolver, transaction, or adapter logic. |
| PF-CLI-003 | MUST | `show` shall be read-only; applicable output shall support human-readable and `--json` forms. |
| PF-CLI-004 | MUST | Mutating `config` commands shall require root, confirmation, and the transaction coordinator. |
| PF-CLI-005 | MUST | `show personaforge plan` shall perform complete validation/resolution without mutation. |
| PF-CLI-006 | MUST | Disruption, reboot, and persistence require manifest policy plus matching CLI options. |
| PF-CLI-007 | MUST | Rollback shall accept only an eligible transaction ID and verify the restored state. |
| PF-CLI-008 | MUST | Footprint commands shall support B0, R1, R2, and B1. |
| PF-CLI-009 | MUST | Nonzero exit categories shall distinguish validation/compatibility, dependency/policy, apply/verification, persistence, and rollback failure. |
| PF-CLI-010 | MUST | CLI values shall never become executable shell fragments. |
| PF-CLI-011 | MUST | No CLI shall expose a raw feature-force, process-kill, `supervisorctl`, or `watchfrr` bypass. |
| PF-CLI-012 | MUST | Runtime commands and their core package shall work after boot without network access or an external controller. |
| PF-CLI-013 | MUST | Build generation shall remain in `sonic-buildimage`, while sharing schema/catalog/resolver contracts with runtime. |

## 7. Build requirements

### 7.1 Public Make contract

~~~bash
make PERSONAFORGE_PROFILE=l3-bgp-leaf-no-lag <platform-image-target>
# Broadcom example when supported by the selected SONiC tree:
make configure PLATFORM=broadcom
make PERSONAFORGE_PROFILE=l3-bgp-leaf-no-lag target/sonic-broadcom.bin
# Additional profiles use the same normal platform target:
make PERSONAFORGE_PROFILE=l3-bgp-bfd-leaf target/sonic-broadcom.bin
make PERSONAFORGE_PROFILE=l3-multirouting-lab target/sonic-broadcom.bin
make PERSONAFORGE_PROFILE=l3-bgp-observability target/sonic-broadcom.bin
~~~

These are independent build selections. Qualification MUST build and inspect each resulting image separately; a successful build of one persona is not evidence for another persona's artifact inventory.

`<platform-image-target>` is the normal image target for any platform supported by the selected SONiC tree. PersonaForge MUST NOT maintain a platform allowlist. The knob value is a profile name, never a path. Make validates/resolves the profile and consumes the generated Make fragment automatically; users do not run a separate preprocessing command.

When `PERSONAFORGE_PROFILE` is unset or empty, PersonaForge MUST make no build-selection change. A non-empty invalid or incompatible value MUST fail before image construction and MUST NOT fall back to a standard image.

Build persistence is image persistence, not ConfigDB persistence. The selected Make variables determine which packages/containers are present in the produced installer image; after that image is installed, its content survives BGP-container, Docker, and node restarts without a runtime save operation. `PERSONAFORGE_PROFILE` and generated Make artifacts are build inputs and do not replace runtime desired state. Runtime `FEATURE`/`FRR_DAEMON` changes remain a separate ConfigDB contract and require authorized `config save` to survive a cold node reboot.

### 7.2 Normative build behavior

| ID | Priority | Requirement |
|---|---|---|
| PF-BLD-001 | MUST | The generator shall emit only catalog-declared variables verified on the pinned baseline. |
| PF-BLD-002 | MUST | Output shall be deterministic and record profile, manifest, catalog, source, generator, and generated-fragment identity. |
| PF-BLD-003 | MUST | Integration shall use an explicit PersonaForge Make include and shall not edit unrelated defaults. |
| PF-BLD-004 | MUST | Post-build inspection shall prove requested optional artifacts absent. |
| PF-BLD-005 | MUST | The image shall boot and pass the persona's functional smoke tests. |
| PF-BLD-006 | SHOULD | `build.reduceFilesystem: true` shall select `BUILD_REDUCE_IMAGE_SIZE=y` only when the selected baseline and platform are qualified for SONiC's slim-image archive and boot path. |
| PF-BLD-007 | MUST | Evidence shall distinguish build omission from runtime disablement. |
| PF-BLD-008 | MUST | Qualification shall compare booted `docker images` inventory and Docker shared/unique storage with the standard build. |
| PF-BLD-009 | MUST | Evidence shall include exact installer bytes and omitted Docker repository/image IDs. |
| PF-BLD-010 | MUST | Top-level Make shall accept `PERSONAFORGE_PROFILE=<name>` with the normal platform image target. |
| PF-BLD-011 | MUST | An unset/empty knob shall preserve the standard build selection path. |
| PF-BLD-012 | MUST | A non-empty value shall resolve only to an allowlisted version-controlled profile; unknown names, absolute paths, traversal, and malformed names shall fail. |
| PF-BLD-013 | MUST | Make shall generate and load `personaforge.mk` at an integration point where its validated settings become the final persona-managed build values. |
| PF-BLD-014 | MUST | Profile, manifest, catalog, source, generator, and fragment changes shall invalidate persona-dependent generated/build outputs. |
| PF-BLD-015 | MUST | Success shall produce the normal SONiC image plus profile-labeled normalized manifest, plan, generated fragment, identity, and verification evidence. |
| PF-BLD-016 | MUST | Invalid, unsupported, or incompatible input shall fail before image construction without silent fallback. |
| PF-BLD-017 | MUST | Generated output shall not set non-catalog variables; conflicting explicit values for persona-managed variables shall fail rather than create ambiguous output. |
| PF-BLD-018 | MUST | `scripts/personaforge-build` shall be an internal Make helper, not a required manual step. |
| PF-BLD-019 | MUST | Platform selection shall not be rejected by the persona schema, profile, catalog, or resolver. The selected platform shall remain in the deterministic build identity to prevent cross-platform cache collisions. |
| PF-BLD-020 | MUST | The `gnmi` capability shall control `INCLUDE_SYSTEM_GNMI` and the `telemetry` capability shall independently control `INCLUDE_SYSTEM_TELEMETRY`; omitting either capability shall not rely on the other capability's build variable. |
| PF-BLD-021 | MUST | Every catalog-declared build variable and `BUILD_REDUCE_IMAGE_SIZE` shall cross the host-to-`slave.mk` boundary with its resolved `y` or `n` value; the slave build shall not fall back to a baseline default that contradicts the persona plan. |
| PF-BLD-022 | MUST | A platform-independent persona shall use the standard ONIE-compatible Docker archive path (`BUILD_REDUCE_IMAGE_SIZE=n`) unless the selected platform is explicitly qualified for SONiC's `docker_inram` slim-image path. Component omission shall continue through existing catalog-declared `INCLUDE_*` controls. |

## 8. Evidence and footprint requirements

### 8.1 Required comparison

| Checkpoint | Image/state | Purpose |
|---|---|---|
| B0 | Standard image before PersonaForge optimization | Baseline and measurement noise. |
| R1 | Same B0 image with selected optional containers disabled | Whole-container memory delta; image inventory must remain unchanged. |
| R2 | Same B0 image with R1 plus an unused running optional FRR daemon disabled | FRR/BGP-container memory delta; image inventory must remain unchanged. |
| B1 | Persona-built image from the same source and manifest | Artifact/Docker-storage delta and booted-memory comparison. |

B0, R1, and R2 MUST use the same installed image. All checkpoints MUST use identical resources, topology, configuration, workload, stabilization interval, and sampling rules. Before measurement, R1 MUST identify at least one running optional container with no configured dependency, and R2 MUST identify at least one running allowlisted optional FRR daemon with no protocol configuration, session, or consumer. A component that was already stopped cannot be counted as a runtime saving.

### 8.2 Reporting requirements

| ID | Priority | Requirement |
|---|---|---|
| PF-RPT-001 | MUST | Plans/transactions/builds shall record release, platform, source, persona/catalog digests, actor where applicable, and timestamp. |
| PF-RPT-002 | MUST | Reports shall show requested, resolved, prior, applied/generated, and observed/proven state. |
| PF-RPT-003 | MUST | FRR evidence shall show daemon administrative state, operational state, and activation method. |
| PF-RPT-004 | MUST | Disruptive FRR evidence shall include BGP, route/FPM recovery, duration, and rollback outcome. |
| PF-RPT-005 | MUST | Build evidence shall include installer bytes, full Docker image inventory, shared/unique storage, and omitted artifacts. |
| PF-RPT-006 | MUST | Footprint results shall use a documented repeatable method. |
| PF-RPT-007 | MUST | Unmeasured values shall be labeled hypotheses; no fixed saving shall be claimed. |
| PF-RPT-008 | MUST | Reports shall redact secrets. |
| PF-RPT-009 | MUST | Memory evidence shall include host `MemAvailable`, per-container cgroup memory, running container/process counts, and per-FRR RSS/PSS when available. |
| PF-RPT-010 | MUST | One report shall compare B0, R1, R2, and B1 under the same workload/sampling window. |
| PF-RPT-011 | MUST | Metrics shall include raw samples, median, variability, absolute delta, and percentage delta. |
| PF-RPT-012 | MUST | Displayed `docker images` sizes shall not be summed as physical storage because layers are shared. |
| PF-RPT-013 | MUST | Docker storage shall use `docker system df -v` shared/unique data and quiescent Docker-root disk use. |
| PF-RPT-014 | MUST | Runtime evidence shall show unchanged image inventory; PersonaForge runtime apply shall not prune images. |

Host, container, and daemon memory views MUST be reported separately to avoid double-counting a daemon already included in container memory.

## 9. Security and quality requirements

| ID | Priority | Requirement |
|---|---|---|
| PF-SEC-001 | MUST | Manifests shall be parsed as untrusted data with a safe, schema-validating loader. |
| PF-SEC-002 | MUST | Components, controls, probes, and activations shall be allowlisted by schema/catalog. |
| PF-SEC-003 | MUST | Manifests/catalogs shall not provide executable paths, hooks, templates, environment expansion, or command strings. |
| PF-SEC-004 | MUST | Snapshots, active intent, and reports shall be root-owned and not world-writable. |
| PF-SEC-005 | MUST | Planning/apply shall not require network access. |
| PF-SEC-006 | MUST | Management-path removal shall require proof of retained authorized access or console recovery. |
| PF-NFR-001 | MUST | Validation, resolution, planning, and build generation shall be deterministic. |
| PF-NFR-002 | MUST | Runtime apply shall be idempotent. |
| PF-NFR-003 | MUST | Existing behavior shall remain unchanged when PersonaForge is unused or FRR daemon state is missing/`default`. |
| PF-NFR-004 | MUST | Every wait/retry shall have a finite timeout and actionable error. |
| PF-NFR-005 | MUST | Unit/integration tests shall cover success and injected failures. |
| PF-NFR-006 | SHOULD | Release-specific logic shall remain in catalogs and typed adapters. |
| PF-NFR-007 | SHOULD | New SONiC/FRR interfaces should be suitable for upstream contribution. |

## 10. Required implementation deliverables

1. Persona schema, `202605` catalog, primary profile, three additional demo profiles, and contract fixtures.
2. Inventory, resolver, immutable planner, transaction coordinator, adapters, and report/evidence core package.
3. Native `config personaforge` and `show personaforge` commands in the pinned `sonic-utilities` repository.
4. `FRR_DAEMON` YANG, supervisor/critical-process integration, `frrcfgd` filtering, and `bgpcfgd` BFD guard.
5. BGP-restart activation, convergence verification, persistence, and rollback; authorized reboot recovery.
6. Make knob/include, build generator, cache/dependency identity, and artifact verifier.
7. Unit tests, selected-platform runtime tests, persona image boot/smoke tests, and failure injection.
8. B0/R1/R2/B1 raw evidence and one comparison report.
9. FRR-native live-control proof of concept when feasible; it is not required to claim restart-activated runtime success.

## 11. Acceptance criteria

Full PersonaForge product acceptance requires all applicable MUST requirements and the following end-to-end outcomes. The current persistence-focused slice has not yet reached this full acceptance gate; its implemented and pending boundaries are stated in Sections 2.1, 6.3, and 6.5.

1. The primary manifest produces a deterministic plan; invalid schema, unknown control, incompatible release/catalog, malformed source identity, or missing required dependency fails before action.
2. Configured PortChannel and other catalog dependencies block conflicting omission with evidence; protected components cannot be disabled.
3. Native `show personaforge plan` performs no mutation, and installed `config/show personaforge --help` exposes the specified commands.
4. A runtime feature action converges, is idempotent, and rolls back after an injected failure without persisting a partial candidate.
5. Missing/`default` `FRR_DAEMON` preserves existing behavior.
6. Disabling one unused running allowlisted FRR daemon produces consistent supervisor/critical expectations; `frrcfgd` and `bgpcfgd` do not recreate or wait for it.
7. BGP-restart activation verifies process, adjacency, route/FPM recovery; an injected failure restores prior intent and verifies recovery.
8. Node reboot is never selected without manifest and command authorization; persisted success survives a cold reboot on the selected qualified target platform.
9. Runtime plan/apply/rollback/status/report and footprint capture work locally on the switch without an external service.
10. A build without `PERSONAFORGE_PROFILE` follows the standard selection path.
11. A valid named profile generates/loads the deterministic Make fragment and produces the normal image plus profile-labeled evidence.
12. An unknown, unsafe, incompatible, or conflicting profile fails before image construction with no standard-image fallback.
13. Changing profile, manifest, catalog, source, or generator invalidates prior PersonaForge-generated state.
14. The persona image omits at least one requested optional Docker artifact, boots, and passes the BGP L3 smoke test.
15. B0/R1/R2/B1 use controlled equivalent conditions and report memory without double counting.
16. B0/R1/R2 show unchanged Docker image IDs; B1 shows verified artifact/inventory and shared/unique storage differences.
17. All savings claims are derived from stored raw evidence rather than fixed assumptions.
18. Restarting a disabled optional feature container does not enable it; desired/observed status reconverges from ConfigDB.
19. Restarting BGP with one disabled allowlisted FRR daemon regenerates matching supervisor and critical-process files, does not respawn that daemon through either configuration owner, and recovers required BGP/routes/FPM.
20. Restarting the PersonaForge controller recovers active metadata and a nonterminal transaction without replaying an uncertain action.
21. `config save` followed by ConfigDB reload preserves a modeled `FRR_DAEMON` row; validation rejects it before the model is installed.
22. Cold reboot with authorized persistence restores and verifies the persona; cold reboot without persistence returns to the saved baseline and reports no false active state.
23. Injected boot-verification failure restores the last-known-good snapshot within the bounded recovery policy, and injected drift is either safely reconciled or explicitly reported according to policy.
24. Runtime restart/reboot checkpoints prove unchanged Docker image inventory.
25. Image upgrade carry-forward is explicitly unsupported: status requires re-inventory and re-plan rather than importing active intent automatically.
26. `l3-bgp-bfd-leaf` produces a distinct deterministic plan/build key, retains LLDP/BFD support, enables `FRR_DAEMON|bfdd`, and preserves verified persisted intent across BGP restart and cold reboot.
27. `l3-multirouting-lab` is exercised in management-framework mode; `ospfd`, `pimd`, and `pathd` are enabled while `bfdd` is disabled, supervisor/critical/configuration-owner expectations agree, and no protocol-convergence claim is made without separate protocol configuration.
28. `l3-bgp-observability` retains the catalog-controlled observability build artifacts, requests enabled LLDP/sFlow/SNMP/gNMI/telemetry rows when present, keeps BFD disabled, and preserves verified persisted intent across restart and cold reboot.
29. The same persona generates successfully for VS, Broadcom, and vendor-specific platform identifiers without a PersonaForge allowlist, while different selected platforms produce different build identities.

## 12. Requirement-to-implementation verification

The table defines required final verification ownership. It is not a claim that every listed test or evidence artifact exists in the current slice.

| Requirement group | Primary verification |
|---|---|
| PF-MAN, PF-INV, PF-RES, PF-PLN | Schema/catalog fixtures, deterministic golden plans, incompatible/unknown dependency tests |
| PF-FEA, PF-TXN, PF-REC | Unit failure injection and selected-platform feature/BGP/controller restart, ConfigDB reload, cold-reboot, recovery, drift, idempotency, and persistence tests |
| PF-FRR | YANG, Jinja, `frrcfgd`, `bgpcfgd`, BGP restart/rollback, and optional live-control tests |
| PF-CLI, PF-SEC | Installed command tests, privilege/policy, no-mutation, injection, permissions, and redaction |
| PF-BLD | Unset-knob regression, named/invalid profile, generated-fragment, stale-cache, artifact, boot, and smoke tests |
| PF-RPT, PF-NFR | Report-schema checks and repeatable B0/R1/R2/B1 measurement review |
