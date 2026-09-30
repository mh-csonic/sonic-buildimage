# PersonaForge Route-Churn and Recovery Comparison

## Purpose

The steady route-scale report measures resource cost while routes are present. This companion test measures transient operational pressure and recovery while the same route state is added and removed. It asks whether the build persona completes useful control-plane churn faster, uses less CPU during churn, or returns memory more effectively than a full image with equivalent services disabled at runtime.

## Workload

The synchronized sequence was:

1. clean baseline with zero benchmark routes;
2. add 2,048 FRR static `/32` routes to `Null0`;
3. add a second 2,048-route block, reaching 4,096;
4. verify all 4,096 routes in the Linux kernel, APPL_DB, and ASIC_DB;
5. remove all 4,096 routes through the same normal FRR command path;
6. verify zero benchmark routes and restoration of the 45-object ASIC route baseline;
7. sample immediate post-cleanup memory and FRR process RSS.

The prefixes came from RFC 2544 benchmark space. No running configuration was saved, and no DUT, SONiC service, or container was rebooted to force cleanup.

## Completion-time comparison

| Treatment | Add 0→2,048 | Add 2,048→4,096 | Total add time | Remove 4,096→0 |
|---|---:|---:|---:|---:|
| DUT-1 full | 416.79s | 1,260.02s | 1,676.81s | 1,725.18s |
| DUT-2 runtime-disabled | 414.67s | 1,258.10s | 1,672.77s | 1,722.44s |
| DUT-3 build persona | 412.67s | 1,249.40s | 1,662.07s | 1,711.43s |

The build persona completed the whole add sequence 14.74 seconds (0.88%) faster than the full image and removal 13.75 seconds (0.80%) faster. Those differences are too small to separate from hardware and run-to-run effects and are not evidence of a persona performance advantage.

The second 2,048-route block took about three times as long as the first block on every DUT. Total add and full removal times were similar, with removal approximately 2.9–3.0% slower. This common nonlinear behavior belongs to the retained FRR/SONiC route path, not to omitted optional services.

## CPU pressure

| Treatment | Add-first-stage mean busy | Add 1s peak | Remove mean busy | Remove 1s peak |
|---|---:|---:|---:|---:|
| DUT-1 full | 43.49% | 99.75% | 44.58% | 100.00% |
| DUT-2 runtime-disabled | 41.56% | 99.50% | 42.52% | 100.00% |
| DUT-3 build persona | 41.24% | 99.00% | 41.69% | 99.50% |

Route churn is a materially stronger CPU test than idle snapshots: it sustained roughly 41–45% CPU busy for long windows and drove every DUT to approximately 100% for individual seconds. Despite that pressure, the three completion times remain within 1%.

The full image is two to three percentage points higher in mean busy time. Because pmon behavior, BIOS revisions, transceiver populations, and source commits differ across nodes, and because the full node still runs four extra optional containers, this is best interpreted as the expected background-service cost—not proof that build omission itself accelerates route processing. DUT-2 has those services stopped and tracks DUT-3 closely.

## Immediate and delayed memory recovery

Routes and ASIC objects returned exactly to baseline, but process memory did not immediately do so.

| Treatment | Container memory above pre-test baseline after cleanup | Host RAM above pre-test baseline | `staticd` RSS after cleanup | `mgmtd` RSS after cleanup |
|---|---:|---:|---:|---:|
| DUT-1 full | 68.4 MiB | 84.5 MiB | 61,220 KiB | 46,812 KiB |
| DUT-2 runtime-disabled | 66.9 MiB | 81.1 MiB | 61,060 KiB | 46,696 KiB |
| DUT-3 build persona | 71.1 MiB | 65.3 MiB | 60,980 KiB | 46,688 KiB |

Before the test, `staticd` RSS was approximately 17–18 MiB and `mgmtd` approximately 22 MiB. At 4,096 routes they grew to about 61 MiB and 47 MiB. Immediate post-cleanup samples show those high-water RSS values retained even though the route count is zero. `zebra` also remained above baseline.

This is **not sufficient evidence of a memory leak**. Allocators commonly retain freed arenas for reuse. A delayed sample approximately four minutes later found `staticd`, `mgmtd`, and `zebra` RSS byte-for-byte unchanged from the immediate sample on every DUT. Delayed active-container memory remained 66.9 MiB, 74.2 MiB, and 72.1 MiB above the respective pre-test baselines. The high-water effect therefore persisted beyond immediate convergence, but a longer soak and repeated cycles would be required to distinguish bounded allocator reuse from unbounded growth.

It is operationally relevant that removing a large route table does not quickly restore the process RSS or host-memory figure that existed before churn. A service restart would confound the comparison and was intentionally not used.

The retention is virtually identical across all treatments. The build persona does not change allocator behavior in the retained FRR daemons.

## Recovery and cleanup proof

After normal command-path removal, every DUT had:

- zero `198.18.0.0/15` benchmark routes in the Linux kernel;
- zero matching APPL_DB route keys;
- no FRR static-route row;
- exactly 45 total ASIC route objects, matching the pre-test baseline;
- `System is ready`;
- zero failed systemd units;
- its original running-container count: 13 on DUT-1 and nine on DUT-2/DUT-3.

No direct Redis deletion, service restart, container restart, DUT reboot, or configuration reload was required.

## Practical conclusion

This churn workload confirms three points:

1. Route add/remove operations create substantial and sustained CPU pressure, making them a better active test than idle CPU sampling.
2. Runtime-disabled and build-persona systems behave almost identically because both retain the same routing stack. Build omission does not materially change route churn throughput.
3. Useful control-plane state, and allocator high-water memory after that state is removed, costs the same regardless of whether unrelated Docker artifacts were excluded from the installer.

For the hackathon presentation, CPU/RAM should therefore be described carefully:

- stopping optional services saves their active memory, whether done by a runtime persona or manually through `FEATURE`;
- a build persona uniquely saves installer and installed artifact storage and removes dormant components;
- it does not make retained FRR route processing inherently faster or more memory-efficient.

## Raw evidence

The main files for each `route-dut1`, `route-dut2`, and `route-dut3` directory are:

- `valid-add-2048-time.txt`
- `add-2048-to-4096-time.txt`
- `route-scale-valid-sar.txt`
- `remove-4096-time.txt`
- `route-remove-sar.txt`
- `baseline/summary.txt`
- `routes-2048/summary.txt`
- `routes-4096/summary.txt`
- `post-cleanup/summary.txt`
- `delayed-post-cleanup/summary.txt`
- per-phase `frr-rss-summary.csv`

Root evidence directory:

`/home/ubuntu/OCP-Hackathon-2026/Persona-Forge/evidence/overnight-ab-study/raw/`
