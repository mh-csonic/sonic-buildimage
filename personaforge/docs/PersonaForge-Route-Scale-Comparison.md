# PersonaForge Route-Scale CPU and RAM Comparison

## Purpose

This test asks a different question from the earlier VRF/object-scale experiment: does a build persona provide more usable CPU or RAM headroom when the retained routing stack is doing real control-plane work?

The workload installs benchmark-only IPv4 `/32` static routes through FRR. Each route traverses FRR `staticd` and `zebra`, the FPM path, SONiC APPL_DB, and ASIC_DB. It therefore consumes active control-plane memory and exercises route programming without requiring external BGP peers or a traffic generator.

## Compared systems

| DUT | Treatment | Running containers | Installed Docker repositories |
|---|---|---:|---:|
| DUT-1 | Full community image, default features | 13 | 28 |
| DUT-2 | Same full image, `gnmi`/`lldp`/`snmp`/`teamd` disabled | 9 | 28 |
| DUT-3 | `l3-bgp-leaf-no-lag` build persona | 9 | 19 |

All three systems use the same Dell S5232F/Broadcom platform, SONiC OS 13, Debian 13.7, kernel line, HwSKU, base route inventory, and 34 configured BGP neighbors. The known BIOS, transceiver, and source-commit differences from the main A/B/C study still constrain small cross-node CPU comparisons.

## Method

- Prefixes: `198.18.0.0/15`, reserved for benchmark testing.
- Route type: FRR static `/32` route to `Null0`.
- Scale points: baseline, 2,048 routes, and 4,096 routes.
- Programming interface: normal `vtysh -c` transactions in batches of 256 commands.
- No `write memory`, `config save`, image reboot, or DUT reboot.
- Convergence requires the same count in the Linux kernel, APPL_DB, and ASIC_DB.
- Each steady scale point uses three synchronized samples containing `mpstat 1 5`, byte-valued `free`, per-container statistics, per-FRR-process RSS, route counts, and system health.
- One-second `sar` records the programming windows.

The first attempt to stream a large integrated FRR configuration through `/dev/stdin` was rejected as a test method because multiple FRR consumers corrupted the shared stream. It installed only 132–135 routes. Those routes were completely removed, all planes returned to their exact baseline of zero benchmark routes and 45 total ASIC route objects, and none of that telemetry is included below.

## Functional convergence

| Scale point | Kernel test routes | APPL_DB test routes | ASIC_DB total routes | Health |
|---|---:|---:|---:|---|
| Baseline, every DUT | 0 | 0 | 45 | Ready, zero failed units |
| 2,048, every DUT | 2,048 | 2,048 | 2,093 | Ready, zero failed units |
| 4,096, every DUT | 4,096 | 4,096 | 4,141 | Ready, zero failed units |

The exact count agreement proves that this was not merely configuration-file scale; all 4,096 test routes reached the SONiC/ASIC object pipeline.

## Programming throughput and CPU pressure

| Treatment | First 2,048 routes | Second 2,048 routes | First-stage mean CPU busy | First-stage 1s peak | Captured second-stage mean CPU busy |
|---|---:|---:|---:|---:|---:|
| DUT-1 full | 416.79s | 1,260.02s | 43.49% | 99.75% | 40.01% |
| DUT-2 runtime-disabled | 414.67s | 1,258.10s | 41.56% | 99.50% | 37.97% |
| DUT-3 build persona | 412.67s | 1,249.40s | 41.24% | 99.00% | 37.46% |

The first-stage time spread is 4.12 seconds (0.99% of the three-node mean). The second-stage spread is 10.62 seconds (0.85%). This is not a meaningful persona separation. The large increase in time for the second block is common to all three nodes and demonstrates nonlinear behavior in the shared FRR/SONiC route-programming path.

The one-second CPU peaks reach approximately 100% on every node. The full-image node is slightly higher in mean busy time, but the difference is small relative to known pmon/idle CPU variability and does not translate into materially different completion time. The second-stage CPU figure covers the first 732 seconds captured by the fixed-duration monitor, not the complete 1,250–1,260 second stage.

## Steady-state host and container memory

Values are medians of three synchronized samples.

| Treatment | Baseline host RAM | 2,048-route host RAM | 4,096-route host RAM | Host increase at 4,096 | Container increase at 4,096 |
|---|---:|---:|---:|---:|---:|
| DUT-1 full | 2,587,762,688 B | 2,639,015,936 B | 2,666,196,992 B | 74.8 MiB | 74.8 MiB |
| DUT-2 runtime-disabled | 2,181,222,400 B | 2,221,285,376 B | 2,264,596,480 B | 79.5 MiB | 77.2 MiB |
| DUT-3 build persona | 2,281,316,352 B | 2,328,059,904 B | 2,351,489,024 B | 66.9 MiB | 80.0 MiB |

Host used-memory deltas include page cache and unrelated platform activity, so active-container memory is the cleaner comparison. The container increase is tightly grouped at approximately 75–80 MiB. The build persona does not require less memory to hold the same active route state.

Steady CPU medians at 4,096 routes were 15.47%, 16.90%, and 16.18% respectively. They overlap the baseline noise and show that route *storage* raises RAM, while route *programming* creates the strong transient CPU pressure.

## FRR daemon memory attribution

Median RSS increase from baseline to 4,096 routes:

| Treatment | `staticd` | `mgmtd` | `zebra` | `bgpd` | Sum of growing FRR daemons |
|---|---:|---:|---:|---:|---:|
| DUT-1 full | 42.0 MiB | 24.0 MiB | 2.8 MiB | 0 | 68.8 MiB |
| DUT-2 runtime-disabled | 42.4 MiB | 24.1 MiB | 3.6 MiB | 0 | 70.0 MiB |
| DUT-3 build persona | 42.3 MiB | 24.0 MiB | 2.7 MiB | 0 | 69.0 MiB |

The almost identical daemon-level slopes are strong evidence that route-state RAM is determined by the retained routing software and route count, not by whether unrelated Docker artifacts were omitted at build time. `bgpd` is flat because this workload uses static routes rather than BGP-learned paths.

## Conclusion

This workload successfully increased both resource dimensions:

- route programming sustained roughly 37–43% mean CPU busy and reached 99–100% one-second peaks;
- 4,096 programmed routes added roughly 75–80 MiB of active-container memory.

It still found no unique build-persona CPU, RAM, or programming-throughput advantage over runtime disabling the same optional services. DUT-2 and DUT-3 retain the same routing stack, so they pay essentially the same incremental cost for useful route state.

The build persona's defensible advantage remains artifact composition: a smaller installer, less installed Docker storage, fewer dormant repositories and service units, and a smaller inactive software/security inventory. Runtime disable reproduces the active-resource benefit while retaining deployment flexibility.

## Raw evidence

Evidence and reproduction helpers are outside the Git worktree:

- `/home/ubuntu/OCP-Hackathon-2026/Persona-Forge/evidence/overnight-ab-study/raw/route-dut1/`
- `/home/ubuntu/OCP-Hackathon-2026/Persona-Forge/evidence/overnight-ab-study/raw/route-dut2/`
- `/home/ubuntu/OCP-Hackathon-2026/Persona-Forge/evidence/overnight-ab-study/raw/route-dut3/`
- `/home/ubuntu/OCP-Hackathon-2026/Persona-Forge/evidence/overnight-ab-study/scale_frr_routes.sh`
- `/home/ubuntu/OCP-Hackathon-2026/Persona-Forge/evidence/overnight-ab-study/collect_route_metrics.sh`
- `/home/ubuntu/OCP-Hackathon-2026/Persona-Forge/evidence/overnight-ab-study/summarize_frr_rss.py`
