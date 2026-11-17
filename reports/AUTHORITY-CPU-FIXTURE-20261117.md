# Private X4 CPU observations, 2026-11-17

These are diagnostic observations on one AMD Ryzen 7 7800X3D, not a
performance benchmark or proof of multiplayer gameplay. Both experiments used
isolated Linux X4 profiles derived from the same confirmed fixture checkpoint,
a private 800×600 virtual display, and running-game-clock receipts bracketing
the observation. The client in the second experiment loaded a later checkpoint
created during admission. Identical scenes, rendering load, camera state,
simulation work and exact loaded bytes were not established.

CPU percentages use one logical CPU as 100%. Process averages below are
weighted by the actual sample intervals. Per-process RSS includes shared
pages; it must not be added as unique physical memory. No frame times or FPS
were measured. The supervisor values cover the Python runner, not Cage,
Xwayland or the outer launcher. Active diagnostics and protected-file checks
contribute load, with materially different overhead between the experiments.

| Observation | Time and samples | X4 CPU | Highest sustained observed thread | X4 RSS | Python runner CPU |
| --- | --- | --- | --- | --- | --- |
| One running X4, completed scope | 60.03 s; 59 samples; largest gap 1.15 s | 218.2% | Movement worker: 53.0% | 4516–4611 MiB | 22.3% |
| Server plus first client, preliminary subset of failed run | 61.65 s; 30 samples; largest gap 2.96 s | Server 283.6%, client 282.2% | Movement workers: server 78.6%, client 78.4% | Server 4652–4780 MiB; client 4514–4592 MiB | 93.6% |

The second row illustrates substantial additional CPU demand while hosting
and playing on the same machine, but does not establish a saturated core, a
frame-rate outcome, behavior in combat or busy worlds, or the cost of a
production server. It is an early comparison, not a controlled measurement of
server overhead. The client simulations and the experimental supervisor have
not yet been optimized.

The later two-client movement-to-server experiment did not succeed. The
client's X4 log recorded throttle start and stop, but the controller did not
confirm the receipts and did not dispatch the server position write. The
supervisor's ordered control cleanup reported an error, while its owned process
list was empty and the outer private scope confirmed cgroup and Xauthority
cleanup. No shared flight, Windows client, Internet connection, trade, combat
or boarding is proven by this run.

Private local evidence, which is not part of the repository:

- Single-instance outer and runner results:
  `.local/private-fixture-single-measure-scope-real-20261117-01/result.json`
  and `overlap-runner/result.json` under the same directory. The latter's
  SHA-256 is `4187ad9fdb222ce466b066414d524e10e3f37875037cb2351f0f5ad5eb56dc5c`.
- Two-instance result and preliminary process report under
  `.local/private-fixture-player-write-scope-real-20261117-01/overlap-runner/`.
  `server/process-measurement.json` has SHA-256
  `1699078ebcde0428575f53eae945ee2e877e5ae922c7b4ca085b8e99a690a799`.
  The enclosing run failed and final client identity reconciliation did not
  complete, so this report remains preliminary even though the partial-result
  validator accepted its source and measurement evidence.
