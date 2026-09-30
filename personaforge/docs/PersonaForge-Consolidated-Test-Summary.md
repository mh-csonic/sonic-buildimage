# PersonaForge Consolidated Test Summary and Honest Assessment

## Executive summary

PersonaForge was evaluated from two perspectives:

1. **Build persona:** create a purpose-built SONiC image containing only the components required for a specific network role.
2. **Runtime persona:** use the standard community SONiC image and disable unnecessary containers or FRR daemons after installation.

The testing confirms that the idea has real value, but the value must be positioned honestly:

> **Build personas reduce what software is physically installed. Runtime personas reduce what software is actively running.**

A build persona demonstrated meaningful image-size, disk-footprint, dormant-software, and software-inventory reductions. It did **not** demonstrate a meaningful additional CPU, RAM, or routing-performance advantage over a full SONiC image with the same optional services disabled through the existing `FEATURE` mechanism.

## Compared systems

| DUT | Image and treatment |
|---|---|
| DUT-1 | Full community SONiC image with default services |
| DUT-2 | Same full image with `gnmi`, `lldp`, `snmp`, and `teamd` disabled using the standard `FEATURE` mechanism |
| DUT-3 | `l3-bgp-leaf-no-lag` build-persona image |

All systems were Dell S5232F Broadcom platforms using SONiC OS 13, Debian 13.7, the same kernel line and HwSKU, and comparable base configurations.

## Tests completed

- Installer binary size
- Installed SONiC image size
- Docker repository and file inventory
- Running container count
- Host process and thread count
- TCP and UDP listener count
- Steady-state CPU and RAM
- Per-container memory
- FRR daemon inventory
- Runtime `FEATURE` persistence
- Runtime-disable transition impact
- Boot and SONiC readiness observations
- 64-VRF and 64-loopback scale
- 4,096-route FRR/kernel/APPL_DB/ASIC_DB scale
- Route programming CPU pressure
- Route removal and churn
- Per-FRR-daemon memory growth
- Post-cleanup allocator memory retention
- Complete cleanup and system-health validation

## Build artifact and storage results

| Measurement | Full image | Build persona | Improvement |
|---|---:|---:|---:|
| Installer binary | 1,133,805,551 bytes | 1,052,909,551 bytes | **80.9 MB / 7.13% smaller** |
| Active installed image directory | 2,837,270,528 bytes | 2,553,987,072 bytes | **283.3 MB / 10% smaller** |
| Docker repositories | 28 | 19 | **32.1% fewer** |
| Docker files | 29,579 | 24,361 | **17.6% fewer** |

This is the clearest unique build-persona benefit. Disabling services through `FEATURE` stopped the containers but did not remove their images. Docker storage remained essentially unchanged.

The build persona physically removed these repositories:

- `docker-dhcp-relay`
- `docker-gnmi-watchdog`
- `docker-lldp`
- `docker-macsec`
- `docker-nat`
- `docker-sflow`
- `docker-snmp`
- `docker-sonic-gnmi`
- `docker-teamd`

This provides a smaller image download and distribution footprint, reduced installation storage, fewer dormant components, a smaller software and vulnerability inventory, and stronger assurance that unnecessary services cannot accidentally start.

## Running containers and active footprint

| Measurement | Full image | Runtime-disabled | Build persona |
|---|---:|---:|---:|
| Running containers | 13 | 9 | 9 |
| Installed Docker repositories | 28 | 28 | 19 |
| Host processes | 334 | 280 | 280 |
| Threads | 832 | 671 | 668 |
| Container PIDs | 320 | 247 | 248 |
| TCP listeners | 17 | 15 | 15 |
| UDP listeners | 7 | 5 | 5 |

Runtime disable and build omission produced almost identical active-process and listener footprints. The difference is that DUT-2 still had the disabled software installed, while DUT-3 did not.

## Steady-state CPU and RAM results

Synchronized six-sample medians:

| Treatment | CPU busy | Host RAM used | Active-container memory |
|---|---:|---:|---:|
| Full image | 20.53% | 2,591,698,944 bytes | 2,219,672,863 bytes |
| Runtime-disabled | 16.81% | 2,180,911,104 bytes | 1,805,559,792 bytes |
| Build persona | 18.10% | 2,286,510,080 bytes | 1,893,273,174 bytes |

Compared with the full image:

- Runtime disable saved approximately **391.8 MiB** of host RAM.
- Build persona saved approximately **291.1 MiB**.
- The build-persona node used approximately **100.7 MiB more** host RAM than the runtime-disabled node in these samples.

This does not mean the build persona inherently wastes memory. The nodes had different BIOS revisions, transceiver populations, pmon behavior, and source commits. However, it clearly means that the study did not demonstrate an additional build-persona RAM benefit.

CPU variation was larger than the separation between systems. pmon CPU frequently dominated the measurements. The active RAM saving comes primarily from stopping containers. The same active-resource benefit can already be achieved using standard SONiC `FEATURE` disable. Removing the corresponding Docker image from disk does not normally reduce RAM further once the process has already been stopped.

No defensible unique build-persona CPU advantage was found.

## Runtime FEATURE persistence

DUT-2 used standard SONiC commands to disable `gnmi`, `lldp`, `snmp`, and `teamd`. After `config save`, those states persisted across restart.

Persistence is therefore not a unique build-persona advantage. Runtime PersonaForge is still useful because it provides a named, validated, repeatable persona workflow instead of requiring operators to manually manage individual `FEATURE` entries.

### Runtime transition cost

Disabling `teamd` while the system was live triggered SONiC dependency handling that restarted `swss`, `syncd`, `radv`, and `bgp`. The system experienced approximately 46–64 seconds of core-container disruption before returning to ready.

Runtime personas are flexible, but applying them to a running node may be disruptive. Build personas start in the intended state and avoid that live transition.

## FRR daemon findings

All three BGP containers ran the same core routing processes: `zebra`, `staticd`, `bgpd`, and `fpmsyncd`. None ran `bfdd`, and no active `FRR_DAEMON|bfdd` configuration was present.

For the selected no-BFD persona, no additional active FRR-daemon saving was demonstrated because BFD was already inactive in the default state. The build persona still expresses and validates the intended role, but this particular daemon choice did not produce an extra measured runtime saving.

## 64-VRF and loopback scale test

Every DUT was configured with 64 additional VRFs, 64 loopbacks, 64 IPv4 `/32` addresses, 128 loopback ConfigDB keys, and 64 kernel VRF devices.

| Treatment | Apply time | Mean CPU during apply | 1-second peak |
|---|---:|---:|---:|
| Full image | 257.79s | 43.14% | 100% |
| Runtime-disabled | 257.61s | 40.83% | 99.5% |
| Build persona | 255.24s | 40.20% | 99% |

The maximum completion-time difference was below 1%. All temporary VRFs and loopbacks were removed afterward. Every DUT returned to zero test VRFs and loopbacks, `System is ready`, and zero failed systemd units.

The workload generated real CPU pressure but showed no meaningful persona-specific performance advantage.

## 4,096-route scale test

The route-scale test added benchmark `/32` static routes through the complete retained routing path:

```text
FRR staticd
    -> zebra
    -> Linux kernel
    -> FPM
    -> SONiC APPL_DB
    -> ASIC_DB
```

At 4,096 routes, every DUT contained 4,096 FRR/kernel test routes, 4,096 APPL_DB route keys, 4,141 total ASIC route objects, a ready system state, and zero failed units.

### Route programming time

| Treatment | First 2,048 routes | Second 2,048 routes | Total |
|---|---:|---:|---:|
| Full image | 416.79s | 1,260.02s | 1,676.81s |
| Runtime-disabled | 414.67s | 1,258.10s | 1,672.77s |
| Build persona | 412.67s | 1,249.40s | 1,662.07s |

The build persona completed the full sequence only 0.88% faster than the full image. That difference is too small to distinguish from hardware and measurement variation.

The second route block took approximately three times longer than the first on every system. This reveals nonlinear scaling in the common FRR/SONiC programming pipeline, not a persona difference.

## Route programming CPU pressure

| Treatment | First-stage mean CPU | 1-second peak |
|---|---:|---:|
| Full image | 43.49% | 99.75% |
| Runtime-disabled | 41.56% | 99.50% |
| Build persona | 41.24% | 99.00% |

This was a much stronger CPU test than idle measurements. All three systems reached approximately 100% CPU for individual seconds, but their completion times remained within 1%.

The full image's slightly higher mean CPU is consistent with its four additional running containers. Runtime-disabled and build-persona behavior was nearly identical.

## Route-state RAM growth

At 4,096 routes:

| Treatment | Host RAM increase | Active-container increase |
|---|---:|---:|
| Full image | 74.8 MiB | 74.8 MiB |
| Runtime-disabled | 79.5 MiB | 77.2 MiB |
| Build persona | 66.9 MiB | 80.0 MiB |

The active-container increase was tightly grouped around 75–80 MiB.

### FRR daemon attribution

Memory increase from baseline to 4,096 routes:

| Treatment | `staticd` | `mgmtd` | `zebra` | `bgpd` |
|---|---:|---:|---:|---:|
| Full image | 42.0 MiB | 24.0 MiB | 2.8 MiB | No change |
| Runtime-disabled | 42.4 MiB | 24.1 MiB | 3.6 MiB | No change |
| Build persona | 42.3 MiB | 24.0 MiB | 2.7 MiB | No change |

The per-daemon memory growth was almost identical. Useful route-state RAM depends on the retained FRR software, route count, and routing functionality. It does not depend on whether unrelated Docker artifacts were removed from the installer.

## Route removal and churn

| Treatment | Removal time | Mean CPU | 1-second peak |
|---|---:|---:|---:|
| Full image | 1,725.18s | 44.58% | 100% |
| Runtime-disabled | 1,722.44s | 42.52% | 100% |
| Build persona | 1,711.43s | 41.69% | 99.5% |

The maximum time difference was below 1%.

After cleanup, kernel benchmark routes, APPL_DB benchmark routes, and FRR static test routes were zero. ASIC route objects returned from 4,141 to 45. Every DUT was ready with zero failed units and its original container count. No reboot, service restart, container restart, or direct Redis deletion was used for cleanup.

## Memory after route cleanup

Although the routes were completely removed, FRR did not immediately return all allocated memory to the operating system.

Approximately four minutes after cleanup:

- `staticd`, `mgmtd`, and `zebra` RSS remained at their high-water values.
- Active-container memory remained approximately 67–74 MiB above the original baseline.
- The behavior was nearly identical on all three systems.

This is not sufficient evidence of a memory leak. Memory allocators commonly retain freed arenas for later reuse. It is still operationally relevant because removing route scale does not immediately restore the original host or container memory measurement. The build persona did not change this FRR allocator behavior.

## Boot-time observation

| Treatment | Total boot | SONiC start-to-ready |
|---|---:|---:|
| Full image | 2m59.038s | 157.49s |
| Build persona | 2m52.143s | 135.61s |

The persona reached SONiC ready approximately 21.9 seconds earlier in this single observation. However, this is not strong enough for a boot-performance claim because only one comparable capture was available, BIOS revisions differed, first-install platform initialization affected timing, and no repeated matched reboot series was performed.

This should be described as suggestive, not proven.

## Current build-omission gaps

The build persona removed nine repositories, but some artifacts expected to be omitted remained:

- `docker-sonic-otel`
- `docker-restapi-sidecar`
- `docker-gnmi-sidecar`
- `docker-mux`

Port 443 remained open through `rest_server`.

MUX was already documented as unsupported. The retained telemetry and REST artifacts are an implementation or claim-boundary gap. Before making stronger minimal-image claims, the project should either remove these artifacts completely or narrow the profile description so it accurately states what is and is not omitted.

## Honest opinion on the hackathon idea

### Is the idea valid?

Yes. The idea solves a real problem: SONiC images contain many components that are unnecessary for specific roles, but those components remain installed even when operators disable them.

PersonaForge provides a structured way to express a device role and apply it at build time or runtime.

### Is build persona mainly a CPU/RAM optimization?

No. The tests do not support that claim.

Once the same services are stopped, the runtime-disabled full image and build persona have almost identical active container count, process count, listener count, route programming performance, VRF programming performance, FRR route-state memory, route churn behavior, and memory high-water behavior.

### Where does build persona provide unique value?

- Smaller installer artifacts
- Reduced installed Docker storage
- Fewer dormant packages and images
- Smaller vulnerability and patching inventory
- Stronger assurance that excluded services cannot be started
- Role-specific image composition
- Potentially faster image transfer and deployment
- Better suitability for constrained or security-sensitive deployments

### Where does runtime persona provide value?

- Compatibility with standard community SONiC images
- No custom image build requirement
- Role changes after deployment
- Repeatable `FEATURE` and FRR-daemon intent
- Persistent configuration
- Nearly the same active CPU/RAM benefit as build personas
- Easier operational adoption

The main weakness of runtime persona is that applying it to a running system may restart dependent SONiC services and cause temporary disruption.

The main weakness of build persona is that it creates additional image variants that must be built, tested, distributed, signed, upgraded, supported, and kept synchronized with community SONiC. The storage and assurance benefit must justify that lifecycle cost.

## Recommended hackathon positioning

The presentation should not claim that build personas inherently use much less RAM than runtime-disabled SONiC, materially accelerate routing, provide proven CPU improvements, are always better than using the `FEATURE` table, or have conclusively proven boot-time improvement.

The presentation can confidently claim:

- A role-specific image was successfully built and installed.
- The build persona was 7.13% smaller as an installer.
- Installed image storage was 10% smaller.
- Docker repository inventory was reduced by 32.1%.
- Unused service artifacts were physically absent.
- Runtime personas provided a repeatable policy on an unchanged community image.
- Runtime persona state persisted.
- Both models supported the same tested routing and VRF workloads.
- The design exposes an honest choice between immutability and flexibility.

## Recommended one-line message

> **PersonaForge lets operators choose between a smaller, purpose-built SONiC artifact and a flexible runtime persona on the standard community image—without pretending that removing inactive files automatically creates additional CPU or RAM savings.**

## Overall verdict

The hackathon idea is technically valid and demonstrable.

Its strongest innovation is not “make SONiC faster.” Its strongest value is:

> **Make SONiC's software composition intentional, role-based, reproducible, and measurable.**

Build personas are most compelling for security-hardened deployments, edge or storage-constrained platforms, controlled appliance-style products, environments where dormant software is undesirable, and large-scale image distribution where artifact size matters.

Runtime personas are likely more practical for general community and data-center operations.

The best overall product direction is to retain both:

```text
Persona definition
        |
        +-- Build realization:
        |      smaller and constrained image
        |
        +-- Runtime realization:
               standard image with flexible persistent policy
```

That combined model is stronger than presenting build persona as a replacement for the existing SONiC `FEATURE` mechanism.

## Detailed documentation

- [Adversarial A/B/C Study](PersonaForge-Adversarial-AB-Study.md)
- [Route-Scale CPU and RAM Comparison](PersonaForge-Route-Scale-Comparison.md)
- [Route-Churn and Recovery Comparison](PersonaForge-Route-Churn-Comparison.md)
- [High-Level Design](PersonaForge-HLD.md)
- [Requirements](PersonaForge-Requirements.md)
- [Implementation and Manual Test Guide](../IMPLEMENTATION-AND-MANUAL-TEST-GUIDE.md)
