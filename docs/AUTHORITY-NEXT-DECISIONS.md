# Authority investigation after the Astra handover

Internal working assessment, 17 November 2026. This note records the user's
clarifications and separates experiments from architecture decisions. It does
not select a new architecture or claim playable multiplayer.

## Current priority: independent clients

The user subsequently redirected work to the clients while they contact
hosting providers about a test server. The approved GPU-free direction remains
recorded below, but further rendering implementation and native server trials
are deferred. No new Vulkan layer was written or tested before this change.

The next client integration step is an independently launched connection using
the existing pinned TLS transport and load owner. The first bounded increment
will request and verify a checkpoint download without fabricating X4 load
observations or claiming admission. Native process ownership, actual load and
pause receipts, and sustained position/velocity application remain required.
Windows integration must reuse applicable native/LAN pieces while replacing
the Linux-specific supervisor boundary; portable Python alone is not proof of
Windows operation.

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
The user explicitly selected **a graphics-free, GPU-free server trial first**,
ahead of the first playable multiplayer flow. This authorizes isolated native
investigation; it does not establish that a fully renderless engine is feasible.

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

The repository also retains a more directly applicable Rust implementation in
`src/rust/x4mp-agent`, documented in `reports/SIM-DECOUPLE-SCHEDULER.txt`.
It preserves the first FrameState flag read and the render-list flip, redirects
only the second read to an owned decision byte, and uses X4's native no-draw
branch. The earlier implementation froze because it also suppressed the flip;
the corrected version now has a bounded native observation, with recurring
vertex-buffer failures that block stable-server acceptance. It retains
renderer initialization, resource processing and render
preparation. Skipping presentation alone would not establish absence of GPU
work; skipping an entire worker would remove simulation or IPC callbacks.

The first bounded trial reuses this agent with software Vulkan for startup,
no GPU device access, and at most about 1,200 skipped draws at fixed20. This is
a precursor to renderless operation, not proof of renderless startup. Both
the Rust agent and the authority native gate patch the fixed-dt sites, so they
must not be combined. `never` plus render-gap zero still forces a draw after
the configured catch-up cap (maximum 3,600 steps); it is not an unlimited
no-render mode. Do not silently remove that bound for this trial.

[The completed observation](../reports/AUTHORITY-NO-GPU-20261117.md) reached
1,217 skipped-draw steps at 20 Hz with continued UI/MD callbacks. Steady X4 CPU
averaged 83.60% of one logical CPU; no saturated thread appeared in that short
window. This is a new-world observation on this machine, not a capacity claim
for Silver's hardware. Dynamic mesh updates failed repeatedly after several
seconds: investigate graphics allocation retirement before another native run.

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

The bounded IPC diagnostic work below and the first GPU-free trial are
complete. Their observations do not satisfy stable-server acceptance.
Continue to measure world progress against wall time, CPU, and UI/MD callbacks;
retain startup and cleanup evidence. Do not remove guards or increase
deadlines merely to make a test pass.

The user clarified the deployment objective: the server must eventually run
on rented game-server hardware, naming Nitrado and 4NetPlayers as examples.
These are examples, not a selected product or authorization to rent/contact
a provider. GPU-free operation and unattended deployment are therefore
portability requirements. The short local observation does not establish a
remote CPU/RAM requirement, independent Steam startup, or hosting acceptance.

Retaining a CPU Vulkan implementation and a virtual display is technically
compatible with a GPU-free Linux target in principle. Removing all graphics
libraries is not itself required by absence of GPU hardware. The user has now
approved **GPU-free Linux with internal graphics libraries** as the next
development stage. Preserve resource lifetimes while suppressing scene
rendering; a stable implementation is still to be demonstrated.
Also distinguish an administrable Linux server from a managed
game-server plan: the reviewed [Nitrado FAQ](https://server.nitrado.net/faqs/index/)
and [4NetPlayers FTP documentation](https://www.4netplayers.com/en/wiki/allgemein/ftp-area/)
describe supported-game files/mods, not a general promise of arbitrary
executables or system dependencies. No provider prohibition or acceptance is
inferred from that documentation gap.

Software Vulkan and a virtual display may remain internally under this decision.
It does not authorize treating the current native experiment as a stable server
or claiming support for a hosting provider. The retired submission-discard
layer does not preserve copies or query semantics and must not be reused
unchanged.

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
or X4 rerun was performed.

The retained full-suite run failed at the apply worker's **initial participant
HELLO ownership check**, before sample selection or a server resume. Both
stand-ins independently expired after 20 seconds, while the worker's 18-second
deadline started after process setup. A single diagnostic rerun of
`test_fourth_real_sample_is_selected` passed in 0.616 seconds without an
ownership rejection, so the historical failure's cause remains unproven.

The apply-worker tests now explicitly keep both stand-ins alive until their
parent closes a control pipe. Other users of the shared fixture retain their
existing lifetime unless they opt in. A regression leaves actual UDP HELLOs
queued for 21 seconds, checks the live processes and their socket ownership
through the production `/proc` checks, receives resume receipts, and verifies
clean exits on EOF. This removes a demonstrated fixture lifetime hazard without
changing production guards or deadlines. All 24 selected tests passed in
32.241 seconds using `python -m unittest discover -s tests -p
'test_authority_client*worker.py' -v` in the isolated worktree. The complete
suite has not been rerun and remains unverified.
