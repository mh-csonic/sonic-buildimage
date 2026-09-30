# PersonaForge Build Persona versus Runtime Disable: Adversarial A/B/C Study

## Executive conclusion

The build persona has a real but narrower advantage than a broad CPU/RAM claim. Compared with the full image, `l3-bgp-leaf-no-lag` reduced the installer by 80,896,000 bytes (7.13%), the active installed image directory by 283,283,456 bytes (10.0%), and the Docker repository inventory from 28 to 19 (32.1%). Those are genuine build-time benefits: a runtime `FEATURE` disable stopped four containers but left all 28 repositories and essentially all Docker storage installed.

It did **not** demonstrate a unique steady-state CPU or RAM benefit over the existing SONiC runtime-disable mechanism. DUT-2 and DUT-3 both ran the same nine-container set and had nearly identical process and listener footprints. In synchronized sampling, CPU distributions overlapped strongly. DUT-3 used about 100.7 MiB more median host RAM than DUT-2, not less; hardware, BIOS, transceiver, pmon, and source-commit differences prevent treating that gap as a persona penalty, but it rules out claiming a measured build-persona RAM win from this experiment.

The 64-VRF/64-loopback workload reached identical functional scale on all three DUTs. Application time was 257.79 seconds on the full image, 257.61 seconds on the runtime-disabled image, and 255.24 seconds on the build persona—a spread below 1% and not a meaningful performance advantage. All test configuration was removed afterward, and every DUT finished ready with zero failed units.

The defensible pitch is therefore: **runtime personas provide flexible, persistent operational policy on a standard community image; build personas provide a smaller and more constrained software artifact with fewer dormant components.** CPU and active RAM savings come mainly from stopping services and can already be reproduced with the standard `FEATURE` table. The implementation must also close or explicitly narrow its telemetry/REST omission claims because several related artifacts remain in the persona image.

## Compared systems

| DUT | Intended treatment | Image | Feature policy |
|---|---|---|---|
| DUT-1 | Full-image control | Full Broadcom image | Leave all default feature states unchanged |
| DUT-2 | Runtime-disabled control | The same full Broadcom image as DUT-1 | Disable `gnmi`, `lldp`, `snmp`, and `teamd`; other persona-omitted features are already disabled by default |
| DUT-3 | Build persona | `l3-bgp-leaf-no-lag` Broadcom image | Optional artifacts omitted at build time; persona runtime intent also disables LLDP and BFD |

All DUTs are Dell S5232F systems using the Broadcom platform. DUT-1 and DUT-2 must use build commit `82223a626`; DUT-3 must use corrected persona build commit `83b4abc1f`. The commit difference is a test limitation: the persona commit includes the PersonaForge integration and ONIE archive correction, whereas the retained full image predates that final correction. Kernel, SONiC release, platform, configuration, and workload are checked separately.

The three pre-study ConfigDB backups have the same table scale and leaf role: 34 BGP neighbors, 68 `INTERFACE` entries, two loopback entries, 34 ports, HwSKU `DellEMC-S5232f-C32`, and local ASN 65100. The files are not byte-identical because node-specific addresses and values differ. The configured BGP neighbors were not established during the initial DUT-2 check; consequently this study is a configured-control-plane and resource experiment, not a line-rate traffic benchmark.

## Hypotheses and falsification criteria

### H1: steady-state CPU and RAM

- Null hypothesis: once the same containers are stopped, the runtime-disabled full image and build persona have equivalent steady-state CPU and available memory within run-to-run noise.
- A build-persona CPU/RAM claim is accepted only if repeated samples show a stable separation larger than within-DUT variation.
- A single `top`, `free`, load-average, or `docker stats` snapshot is not sufficient evidence.

### H2: installed storage and image inventory

- Runtime disable should stop containers but should not remove their Docker images.
- Build omission should remove selected images and reduce installer and installed-image storage.
- The claim is falsified if DUT-3 retains the same omitted image IDs or consumes indistinguishable installed storage after controlling for old image slots and mutable logs.

### H3: boot and readiness

- Fewer services may reduce userspace boot-to-ready time, but platform firmware dominates total boot time.
- The claim is accepted only from repeated reboot cycles and the SONiC `System is ready` event, not merely `systemd-analyze` graphical-target timing.

### H4: persistence

- DUT-2's standard `FEATURE` states should persist after `config save` and reboot.
- DUT-3's omitted artifacts should remain absent after reboot without requiring a runtime stop action.
- If DUT-2 reliably persists the same operational state, persistence alone is not a unique build-persona advantage.

### H5: scale behavior

- Identical VRF and loopback scale is applied to all DUTs.
- The scale test checks functional parity and whether reduced background services materially change CPU/RAM headroom; it does not imply that removed services accelerate BGP or ASIC programming.

## Test controls

1. Verify exact image commit, platform, HwSKU, kernel, health, and failed systemd units before collecting data.
2. Back up `/etc/sonic/config_db.json` from every DUT before mutation.
3. Use the same configuration and scale workload on all three DUTs.
4. Let first-boot installation and service initialization settle before baseline sampling.
5. Capture at least three samples per phase, five minutes apart; use six for the primary full-image baseline. Each sample contains `mpstat 1 5`, byte-valued `free`, load average, and per-container statistics.
6. Record both logical Docker image sizes and actual host/filesystem usage because Docker layers are shared.
7. Save raw command output with UTC timestamps; retain negative and anomalous results.
8. Restore original configurations after destructive scale testing.

## Artifact-size evidence

| Installer | Bytes | Difference from full |
|---|---:|---:|
| Full Broadcom (`82223a626`) | 1,133,805,551 | — |
| `l3-bgp-leaf-no-lag` (`83b4abc1f`) | 1,052,909,551 | 80,896,000 bytes smaller (7.13%) |

SHA-256:

- Full: `15152800ee5a2cce8e21bfd4b4ad0fd5477b9d2a5f6246da9c7f6db769e34184`
- Persona: `570757528ec4ec51975489b809a6c8061a7cb499ed4010c249a7204abb146974`

This installer-size reduction is a genuine build-time benefit and cannot be produced by disabling `FEATURE` rows after installation. It must not be confused with an 80.9 MB runtime-memory saving.

## Results

### Image identity and health

DUT-1 and DUT-2 run the identical full build `82223a626`; DUT-3 runs the corrected persona build `83b4abc1f`. All report the same SONiC OS 13, Debian 13.7, kernel `6.12.41+deb13-sonic-amd64`, Broadcom ASIC, Dell S5232F platform, and DellEMC-S5232f-C32 HwSKU. All were `System is ready` with zero failed systemd units when synchronized collection began.

### Containers and Docker images

DUT-1's full image runs 13 containers from 28 unique repositories. Disabling `gnmi`, `lldp`, `snmp`, and `teamd` through `config feature state --block` reduced DUT-2's running set to nine, but all 28 unique repositories remained installed. Actual `/var/lib/docker` usage was effectively unchanged: 2,220,617,728 bytes before and 2,220,601,344 bytes immediately after disable. The 16,384-byte difference is noise, not artifact removal.

DUT-3's build persona runs the same nine-container service set as DUT-2 but contains only 19 repositories. The nine repositories absent from the build persona are `docker-dhcp-relay`, `docker-gnmi-watchdog`, `docker-lldp`, `docker-macsec`, `docker-nat`, `docker-sflow`, `docker-snmp`, `docker-sonic-gnmi`, and `docker-teamd`. The corresponding systemd services for gNMI, LLDP, SNMP, and teamd are absent on DUT-3, whereas they remain installed but masked on DUT-2.

The artifact result is not perfect. `docker-sonic-otel`, `docker-restapi-sidecar`, `docker-gnmi-sidecar`, and `docker-mux` remain in DUT-3. MUX was already recorded as unsupported by the build plan. More seriously, the plan reports telemetry and REST API as `omitted`, while their Docker artifacts remain. Port 443 (`rest_server`) is still listening on all three DUTs. This is an implementation/evidence gap that must be fixed or described more narrowly.

This directly confirms the expected distinction: runtime disable removes active processes but does not provide an installed-image or dormant-software reduction.

### Runtime process and listener footprint

At one synchronized checkpoint, DUT-1 had 334 host processes, 832 threads, and 320 container PIDs. DUT-2 had 280/671/247, and DUT-3 had 280/668/248. Runtime disable and build omission therefore produced essentially the same active-process footprint.

DUT-1 had 17 TCP and seven UDP listeners; DUT-2 and DUT-3 each had 15 TCP and five UDP listeners. The full image's extra externally relevant listeners were telemetry on TCP/8080 and SNMP on UDP/161 (plus the corresponding local SNMP listener). Runtime disable and build omission closed the same listeners. All three still exposed `rest_server` on TCP/443, consistent with the retained REST sidecar gap.

### FRR daemon realization

All three BGP containers ran the same core FRR set (`zebra`, `staticd`, `bgpd`, and `fpmsyncd`); none ran `bfdd`, and no `FRR_DAEMON|bfdd` row was present. For this selected no-BFD persona, the build image provides no additional active-daemon reduction beyond the baseline/default runtime state.

### CPU and memory

The six-sample full-image baseline on DUT-2 had:

- median used RAM: 2,555,324,416 bytes;
- mean used RAM: 2,557,766,315 bytes;
- median CPU busy: 18.47%;
- CPU-busy standard deviation: 11.40 percentage points.

The three settled pre-reboot runtime-disabled samples had median used RAM of 2,234,503,168 bytes, 320,821,248 bytes (306.0 MiB, 12.6%) below the full-image median. The three post-reboot samples had a still-lower median of 2,171,736,064 bytes; the difference between the two runtime-disabled phases shows why cross-phase cache state must be treated cautiously. Both reductions closely match the full-image cgroup snapshot for the four targeted containers: 303.09 MiB in total (`gnmi` 152.6 MiB, `snmp` 60.11 MiB, `lldp` 58.64 MiB, and `teamd` 31.74 MiB). The evidence therefore attributes the RAM saving to stopping those services, not to removing their image layers.

Median CPU busy changed from 18.47% to 17.43% before reboot, only 1.04 percentage points. The post-reboot median was 21.00%. Both differences are much smaller than the full-image phase's 11.40-point standard deviation and cannot support a credible CPU advantage claim. The first post-disable sample is explicitly excluded because it was captured while core services were restarting.

The synchronized six-sample cross-DUT comparison produced the following medians:

| Treatment | CPU busy | Host RAM used | Active-container memory | pmon CPU |
|---|---:|---:|---:|---:|
| DUT-1 full | 20.53% | 2,591,698,944 bytes | 2,219,672,863 bytes | 53.67% |
| DUT-2 runtime-disabled | 16.81% | 2,180,911,104 bytes | 1,805,559,792 bytes | 43.12% |
| DUT-3 build persona | 18.10% | 2,286,510,080 bytes | 1,893,273,174 bytes | 36.88% |

Relative to DUT-1, median host RAM was 410,787,840 bytes (391.8 MiB, 15.85%) lower on DUT-2 and 305,188,864 bytes (291.1 MiB, 11.77%) lower on DUT-3. DUT-3's median was 105,598,976 bytes (100.7 MiB) *higher* than DUT-2's. Active-container memory showed the same direction, with DUT-3 approximately 87.7 MiB above DUT-2. These cross-node differences include pmon and hardware/commit effects and are not causal estimates, but they provide no evidence of an additional build-time RAM benefit after the same active services are removed.

CPU-busy standard deviations were 7.44, 10.53, and 9.62 percentage points for DUT-1, DUT-2, and DUT-3 respectively. That variation is larger than the median separation. The CPU distributions overlap and do not support a build-persona CPU ranking.

Cross-node CPU comparisons are additionally dominated by platform monitoring. Snapshot pmon CPU ranged from below 1% to approximately 60%, despite identical switch model and six operational links on each DUT. The nodes have different BIOS revisions and transceiver populations. CPU is therefore reported as “no demonstrated build-persona advantage,” not as a precise ranking.

### Installed disk usage

On DUT-2 before disable, `/host` consumed 2,914,287,616 bytes and `/var/lib/docker` consumed 2,220,617,728 bytes. Immediately after runtime disable, the corresponding values were 2,914,496,512 and 2,220,601,344 bytes. Runtime disable therefore produced no meaningful installed-storage saving.

The current full-image directory on DUT-1 consumes 2,837,270,528 bytes versus 2,553,987,072 bytes for the current build-persona directory on DUT-3: a 283,283,456-byte (10.0%) reduction. Their Docker subdirectories differ by approximately the same amount (2,220,666,880 versus 1,937,674,240 bytes), while `fs.squashfs` differs by only 20,480 bytes. Thus the installed saving comes almost entirely from omitted Docker content. Docker-file count falls from 29,579 to 24,361 (17.6%). Total `/host` usage is not compared because DUT-1 and DUT-3 retain different older fallback image slots.

### Reboot and persistence

DUT-2 persisted all four standard FEATURE settings across reboot: `gnmi`, `lldp`, `snmp`, and `teamd` remained `disabled`, while their Docker images remained present. After delayed services initialized, the system returned to ready with no failed units. This proves that persistence is not a unique build-persona benefit; standard SONiC configuration already preserves the disabled state when saved.

A separate operational finding is also proven: the live runtime transition was disruptive. Disabling `teamd` caused SONiC's service dependency chain to stop and restart `swss`, `syncd`, `radv`, and `bgp`. Journal timestamps show approximately 46–64 seconds of core-container downtime before the system recovered to ready with no failed units. This is a transition-cost observation, not evidence of steady-state instability.

Available first-install captures are suggestive but not sufficient for a boot claim. DUT-1 full reported 2m59.038s total and 2m03.406s userspace; its SONiC start-to-ready interval was 157.49s. DUT-3 persona reported 2m52.143s total and 2m00.785s userspace; start-to-ready was 135.61s. The persona reached ready 21.9s earlier in these single captures, while total boot differed by only 6.9s and userspace by 2.6s. Different BIOS revisions, one-time platform setup, and the lack of repeated matched reboot cycles make this an observation, not proof of a persona boot advantage. No additional DUT reboot was performed for this study.

### VRF/interface scale

All three DUTs concurrently accepted 64 additional VRFs, 64 bound loopbacks, and 64 IPv4 /32 addresses using supported SONiC CLI commands. Each finished with 64 matching VRF keys, 128 loopback parent/address keys, 64 kernel VRF devices, and 64 test loopbacks. System health remained ready.

| Treatment | Apply time | Mean CPU busy during first 260s | Peak 1s CPU busy | `kbmemused` range | At-scale median RAM |
|---|---:|---:|---:|---:|---:|
| DUT-1 full | 257.79s | 43.14% | 100.0% | 275,532 KiB | 2,594,877,440 bytes |
| DUT-2 runtime-disabled | 257.61s | 40.83% | 99.5% | 211,496 KiB | 2,194,874,368 bytes |
| DUT-3 build persona | 255.24s | 40.20% | 99.0% | 162,544 KiB | 2,301,206,528 bytes |

The 2.55-second maximum apply-time difference is below 1%; it does not establish a persona performance benefit. Three synchronized at-scale samples had median CPU busy of 17.84%, 17.39%, and 19.94% respectively—again overlapping normal noise. Compared with each node's synchronized non-scale median, used RAM increased by only about 3.0 MiB on DUT-1, 13.3 MiB on DUT-2, and 14.0 MiB on DUT-3. DUT-3 remained roughly 101 MiB above DUT-2, consistent with the baseline rather than a scale-induced separation.

Supported-CLI cleanup took 216.39, 214.70, and 212.84 seconds respectively. Independent post-cleanup checks on every DUT proved zero matching ConfigDB VRF keys, zero matching loopback keys, zero kernel test VRFs, and zero test loopbacks. All three finished `System is ready` with zero failed units; DUT-1 returned to 13 running containers and DUT-2/DUT-3 to nine.

## Interpretation for the hackathon presentation

The presentation should separate two value propositions:

1. Runtime personas automate and persist an operational policy using an unchanged community image. Their likely CPU/RAM result should be similar to manual `FEATURE` disable because both stop the same processes.
2. Build personas create a smaller immutable artifact. Their defensible unique advantages are smaller installer/transfer footprint, absence of unused Docker artifacts on the node, reduced dormant software and vulnerability inventory, and less ambiguity about what can execute.

The repeated CPU/RAM results did not show a meaningful build-persona lead over runtime disable. That is not a failed experiment; it narrows the honest claim. Build personas optimize artifact composition, transfer/storage, dormant-software exposure, and assurance. Runtime personas optimize deploy-time flexibility and reproduce the active resource benefit without a custom binary. The full-image control consumed more active memory because the four optional containers remained running.

## Limitations

- DUT-3 and the two full-image DUTs use different source commits, although they share the same SONiC release, kernel line, platform, and build host. Results tied to component presence are strong; small CPU/RAM differences remain susceptible to commit-level variation.
- Logical `docker images` sizes double-count shared layers. Actual filesystem usage and unique-layer accounting are reported separately.
- Hardware is the same model, but BIOS/firmware revisions and physical port state may differ. Firmware time is therefore separated from userspace readiness.
- Idle CPU is noisy. Repeated samples and within-DUT variance are required.
- The scale workload validates the selected BGP-leaf use case; it is not a universal SONiC performance benchmark.
- BIOS revisions differ across the three nominally identical platforms (`3.40.0.9-7`, `-10`, and `-11`), installed memory differs by up to about 20 MiB, and the transceiver populations differ. These facts constrain cross-node CPU/boot conclusions.
- The BGP peers were configured but not established and no traffic generator was attached. The study measures control-plane configuration and idle/management resource behavior, not forwarding throughput, convergence under traffic, or route-scale programming.
- Build omission was assessed from the installed repositories and service units actually present, not only the generated build-plan text. Retained telemetry, REST, gNMI-sidecar, and MUX artifacts limit the current reduction.

## Raw evidence

Follow-up active-pressure comparisons are documented separately:

- [Route-scale CPU and RAM comparison](PersonaForge-Route-Scale-Comparison.md)
- [Route-churn and recovery comparison](PersonaForge-Route-Churn-Comparison.md)

Raw output is retained outside the Git worktree under:

`/home/ubuntu/OCP-Hackathon-2026/Persona-Forge/evidence/overnight-ab-study/raw/`

The collector used for reproducibility is:

`/home/ubuntu/OCP-Hackathon-2026/Persona-Forge/evidence/overnight-ab-study/collect_dut_metrics.sh`
