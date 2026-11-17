# Authority investigation after the Astra handover

Internal working assessment, 17 November 2026. This note records the user's
clarifications and separates experiments from architecture decisions. It does
not select a new architecture or claim playable multiplayer.

## Performance question

The relevant question is the capacity of **one authoritative X4 instance on a
separate server**, including networking and state import. Running a server and
two clients on the development PC does not answer it. The user recalled
Silver describing a "ryzen milan type server"; the exact CPU, graphics path,
world, software version and measurements are unavailable. Do not infer those
details or treat the recollection as a benchmark.

The server should ultimately perform simulation without producing graphics.
The current full-X4 launch path still initializes graphics. A private or
virtual display does not demonstrate that rendering has stopped.

Existing observations:

- [The current CPU report](../reports/AUTHORITY-CPU-FIXTURE-20261117.md)
  records about 218% CPU for one X4. The separate two-instance observation
  includes about 94% for its Python supervisor. These diagnostic workloads
  are not a controlled measure of simulation-only server capacity.
- The historical local H0 experiment ran one X4 with Mesa software Vulkan,
  with GPU device access masked. Its steady sample used about 11.86 CPU
  seconds per wall second; UI callbacks averaged about 2.21 per engine-real
  second. It did not measure pure simulation cost or establish a wall-clock
  simulation rate. The report is retained at
  `../../x4-weapons-7-4/reports/HEADLESS-H0-20261025.txt`.
  This is not known to be Silver's test.
- The failed throttle experiment has a statically identifiable deadline-risk
  path: repeated aggregate process/file/connection guards execute inside one
  short receipt deadline. Its old failure discarded the specific exception.
  Diagnosing guard cost does not establish the cause of that historical run.

Measure simulation progress against external elapsed time, command/receipt
latency, X4 CPU and supervisor CPU separately. Record the actual renderer and
compare the same save and scene before attributing a change to networking or
authority. Process CPU alone does not establish either capacity or a
single-thread bottleneck. Excluding rendering must preserve the simulation,
MD events and the callbacks currently driving local IPC.

The current Linux gate exposes a pre-`FrameTick` admission boundary and the
VBI table address (`src/native/engine/linux/gate_linux.c` and `gate_sites.h`).
`gate_runtime_ids.h` identifies GameRender as VBI slot 10; the UI overlay probe
wraps that callback. These are existing inspection points, not rendering
suppression. The Windows render-frame study describes simulation and render
preparation on the same MoveWorker, with drawing/presentation on the main
thread. Its render-only frames skip simulation while retaining graphics, so
that feature cannot simply be used as a simulation-only mode.

The next rendering investigation should map the corresponding Linux
preparation, submission and synchronization boundaries. Skipping presentation
alone does not establish that scene preparation and GPU work stop; skipping
an entire worker would also remove simulation or IPC callbacks. No render
patch or new native run has been authorized by this note.

## Sector ownership proposal

The user suggested assigning a whole occupied sector to one client to avoid
frequent ownership changes as a player's attention area moves. This is a
candidate to test, not an implemented policy. A sector can be the ownership
unit while the responsible X4 still uses multiple native attention levels.
Sector ownership does not require forcing every object into high attention.

The decisive engine requirement remains selective suppression of competing
simulation while keeping remote objects available to queries and state import.
`set_space_jobs_allowed` is not documented as a general simulation switch;
the [existing case](../tools/dev/AUTHORITY-SECTOR-JOBS-CASE.md) does not prove
one. Two distant players within a single sector must remain possible: one
owner's ordinary camera-relative simulation cannot simply be assumed to
provide both players' detailed combat.

Ship crossings, simultaneous trade against a shared account, disconnects and
checkpoint publication still need explicit ownership and completion rules.
Delegation to the local player's process is not work offloaded to a different
computer. Remote delegation can reduce host work only when the corresponding
host simulation actually stops.

The older lockstep attention study is useful evidence of engine coupling.
Its requirement for equal state on every peer at the same tick belongs to
lockstep. Our authoritative proposal does not inherit that requirement;
replicas may lag. That distinction does not by itself supply a mechanism for
stopping local AI, accepting results or transferring a live simulation.

## Immediate work and decision boundary

Use the existing evidence before new native runs. First attribute the bounded
IPC failure path with an offline test and fixed timing counters; do not remove
guards or increase deadlines merely to make a test pass. Locate existing
Linux rendering/simulation separation work before proposing a native patch.

Any decision to adopt sector-wide ownership, change the ownership of economy
or combat, or commit to a new server execution model must be discussed with
the user. A useful first selective-simulation experiment would involve a
single enrolled free ship, continued progress elsewhere, imported state, and
resumption of that ship. Its controls must demonstrate behavior rather than
merely acknowledge a setter. Do not rerun a complete multi-X4 scenario just
to investigate a local IPC failure.

## Bounded offline result

An actual localhost UDP test of the throttle receiver now queues valid
STARTED/STOPPED receipts and injects elapsed time into its external guard.
The receiver times out before reading STARTED, after sending GO exactly once.
This reproduces a possible failure mechanism, not the historical native
failure. Fixed call counts and elapsed times for external guards, socket-owner
checks and pumping are now included in the redacted uncertainty report.
Pump time includes its nested guard work; these counters do not cover every
part of the receiver or measure CPU time. Protocol, deadlines and ownership
checks are unchanged. All 16 tests in the impacted module passed; no full-suite
or X4 rerun was performed. The earlier full-suite failure remains open.
