# Isolated source-to-client motion buffer diagnostic

On 2026-11-16, `.local/authority-source-motion-pair-01` returned
`success=false` with a source or participant owner fault and reported that
owned-process cleanup was confirmed. The source X4 log recorded
`binding → attaching → await_go → observing → reading → delivering`, followed
by a generic source `ERROR`. The separate client X4 log recorded a successful
local apply of index 10055 after a witness selection; it did not record a
motion `BUFFERED` marker. The process clocks are not synchronized, and the
logs do not record TCP frames, the source MD acknowledgement, REARM, the
specific faulting component or any actor/sector-binding predicate. Therefore
neither the precise cause nor the outcome of the in-flight job and motion
request is established. No source-to-client motion sample was demonstrated.

After that failed run, bounded opt-in diagnostic reason codes were added for
the source job, local motion IPC and sampler stages. The actor conversion and
dock-check substage can be named without logging actor handles or raw property
values. These codes do not retroactively diagnose the first failed run.

A second isolated attempt, `.local/authority-source-motion-pair-02`, also
returned `success=false` with confirmed owned cleanup. Its client log again
recorded local apply for index 10055; no client `BUFFERED` marker was recorded.
The source log recorded `sampler register_id_roundtrip sampler_register`. This
locates the failure in the sampler's local LuaID identity checks but does not
identify which check failed or the actual returned LuaID type; there is no
packet trace or independently recorded source acknowledgement frame.

The reviewed sampler did contain an incompatible check: it rejected all
opaque Lua `userdata` before converting them back to uint64. The revised code
allows userdata only as an opaque input to `ConvertIDTo64Bit`, then requires
the result to equal the independently retained exact actor uint64. Numeric and
cdata inputs still additionally require an exact direct check. LuaJIT tests
exercise real userdata, wrong and rounded reverse conversions and a uint64
above 2^53. An opaque userdata return is a plausible explanation of attempt 02,
not an observed return type or a proven cause.

A third isolated attempt, `.local/authority-source-motion-pair-03`, returned
`success=false` with `pair context changed`; owned cleanup was reported
confirmed. The source X4 log reached `done`, and the separate client log
recorded `LOCAL_APPLIED 10055`, then
`BUFFERED 10055 1 cluster_115_sector001_macro 13.25216319499998`. The marker
is emitted after the local MD/FFI binding and buffer push but before its UDP
reply. It is therefore provisional evidence of that client-side step, not a
retained TCP receipt or proof of complete delivery. The logs have independent
game clocks and no packet trace; the precise worker outcome is not retained.

The `pair context changed` message identifies expiry of the coordinator's
deadline, capped at 110 seconds, in this run's guard path; other failed lifecycle
checks would have raised their own errors. The terminal-result reader at that
revision performed the full expensive guard before and after every individual
byte. That design can exhaust the deadline on a long result and was replaced
afterward by bounded chunked framing with the same guard/deadline checks and
strict rejection of buffered or newly received trailing bytes. The available
artifacts do not establish whether result reading was the actual cause of this
particular timeout. The revision is tested offline only; this is not a native
successful end-to-end result.

## Fourth attempt: one read-only sample

On 2026-11-16, `.local/authority-source-motion-pair-04` reported `success=true`
and confirmed cleanup with no owned processes remaining. The source X4 log
recorded the ordered states `binding → attaching → await_go → observing →
reading → delivering → done`. The separate client X4 log recorded witness
1318 accepted in `cluster_115_sector001_macro`, `LOCAL_APPLIED 10055`, and
`BUFFERED 10055 1 cluster_115_sector001_macro 13.382891193000006`. Both X4
instances were requested to load the staged checkpoint; the expected marker
and pause were observed. The result does not establish exact file consumption
by X4.

The saved result reports one source sample for index 10055, sequence 1, in that
sector at source game time 13.382891193000006: position
`(-132216.359375, 6004.388671875, 169077.640625)` and `velocity: null`. It
also reports a source queue acknowledgement, client binding/buffering and no
pose application. The source log does not independently list this sample or
the TCP/UDP acknowledgement frames. The worker and runner code require source
REARM, local binding, a client reply after its buffer push and a TCP receipt for
the saved success result; the client marker independently corroborates the
buffer step, but precedes its reply. No packet trace or separate raw worker
JSON was retained. PID/socket ownership checks are likewise supported by the
code and result, without retained raw PID/inode observations. Source and client
game clocks are independent.

This one local Linux/Linux observation uses synthetic admission/checkpoint
proof and an artificial client creation seed with approximate loadout. A job
activation does not prove a birth; the source descriptor is non-atomic. The
sample does not establish common sector frames, measured or derived velocity,
continuous movement, a pose or velocity write, a visual flight result, full
universe coverage, gameplay, Windows or Internet operation.

## Fifth attempt: two source samples

On 2026-11-16, `.local/authority-source-motion-pair-05` reported
`success=true` and confirmed cleanup with no owned processes remaining. The
source X4 log recorded `binding → attaching → await_go → observing → reading →
delivering → done`. The separate client log recorded witness 1318 accepted,
`LOCAL_APPLIED 10055`, and two `BUFFERED` markers for index 10055 in
`cluster_115_sector001_macro`: sequence 1 at source time
13.394301519000008 and sequence 2 at 13.570402863000011.

The saved result reports the following positions for those two samples:

| Sequence | Source game time | Position `(x, y, z)` | Velocity |
| --- | --- | --- | --- |
| 1 | 13.394301519000008 | `(-132216.46875, 6004.3916015625, 169078.03125)` | `null` (unknown) |
| 2 | 13.57040286300001 | `(-132215.296875, 6004.4482421875, 169072.640625)` | `(6.65454887158602, 0.32163652879332433, -30.610924809295692)` |

The second vector is calculated from the two local position readings per
**source game second**, not read as native X4 velocity or calibrated against
wall time. The source sampler's code requires the retained actor/registry
binding and local sector reference to remain valid and derives the rate only
for the same local frame and an allowed finite time interval. It does not make
the position and time reads atomic or establish a common frame with the client.

Each `BUFFERED` marker is emitted after the client's local MD/FFI binding and
hold-only buffer push, but before its reply. The worker/runner code requires a
TCP receipt for each sample and validates the second rate against the first
sample before transmission. The saved success result supports those code paths;
no packet capture or separate raw worker JSON was retained. The markers and
saved sample values are different kinds of evidence. Source and client game
clocks are independent. Both load requests, expected markers and pauses were
logged; exact file consumption by X4 is not independently established.
Both staged save hashes matched the reported checkpoint digest. The sampled
source sampler/session/owner and client owner/binding/session scripts matched
the reviewed sources; the client buffer had its expected global export. This
was not a complete overlay audit, and no raw PID/inode record was retained.

The observation concerns one registered actor, one local Linux client and one
sector. Admission/checkpoint proof and client creation seed are synthetic; the
replica loadout is approximate. The client buffer stores the samples in
hold-only mode; neither pose nor velocity was applied to the ship. A job
activation does not prove a birth. This is not evidence of visible flight,
combat, trading, independent sectors, complete world coverage, Windows or
Internet multiplayer.

`authority_source_motion_pair_live.py` is a default-off, single-event diagnostic
using the existing private two-X4 lifecycle. It stages the pinned census save
and its historical registry fixture into separate isolated source and client
profiles. The TCP coordinator admission and checkpoint proof are synthetic;
the client's ship creation uses an explicitly artificial seed (7183) and
approximate loadout. An activation is not proof of a ship's birth.

The intended success condition is a source job acknowledged by the client and
the source MD queue, followed by REARM and one sampled source position over
local UDP/TCP to the client. The client performs a correlated local MD/FFI
registry binding and pushes the complete sample to its 3D hold-only buffer
before returning a receipt. The result is correlated with the client BUFFERED
log marker, which by itself is provisional until the receipt and worker result.
The first velocity is unknown, not a fabricated zero. The diagnostic has no
pose/velocity writer and does not prove visual movement, native velocity,
atomic sampling, cross-process sector frame equality, persistence, gameplay,
Windows, Internet transport or complete universe coverage.

The opt-in `--motion-count 2` variant waits for two independently receipted
samples of the same confirmed source registry entry and checks both correlated
client buffer markers. Sequence and source game time must increase; the first
velocity must be unknown. Before transmitting the second sample, its sector,
identity and any available rate are checked against the first position and the
source-game-time difference. A valid zero vector or an unknown second velocity
is allowed; a nonzero movement is not required. The source sampler checks its
retained local actor and sector reference for each read. These checks do not
prove actor lifetime across arbitrary reuse, atomic reads, an equivalent client
frame, source-to-client clock synchronization, motion application or smooth
flight. This mode is bounded test instrumentation, not a limit on the number of
events in the intended implementation.

The runner inherits the pinned executable/save, load-marker, private profile,
owned-process cleanup and exclusive-lock fences of the existing pair runner.
Both additional local UDP sockets require PID/start/executable/socket-inode
checks by the worker; lease/attempt tokens are fresh. A single update owner per
X4 and one serial TCP delivery owner are required. A blocked motion operation
can delay an incoming job until its own deadline; the test fails closed in that
case and makes no scheduling-liveness claim. The supervisor must fence both
processes and retain profile locks until cleanup is confirmed on any failure.

Offline tests use simulated X4 ABI/MD, and any future native run needs
independent static review, a fresh
private output directory, a display owned by that run and verified cleanup.

## Optional saved-registry diagnostic

The separate `--saved-index INDEX` path selects exactly one eligible index from
the checksum-pinned census witness artifact and its one saved sector. Both
private instances receive opt-in saved-baseline readers; their ordinary marker,
pinned save, isolated process and socket guards remain in force. The source
registers that actor locally via `REGISTER_SAVED`; the Python bridge creates a
motion track only after the correlated local registration response. The client
resolves the same registry index in its own saved registry and reports a
hold-only buffer push. There is no invented job receipt or ship creation.

During the saved attempt the source's observed job-owner phase must remain
`observing`; the worker also rejects an unexpected source-job packet before
or during motion operations. These checks are point-in-time guards and do not
prove atomically that no job activation occurred between observations. A
competing job, unavailable or docked actor, sector change, timeout, guard loss
or uncertain operation fences the experiment; none is automatically retried.
The selected index's saved-sector eligibility does not guarantee a live actor.
The expected marker and pinned staging are not independent proof of the exact
file consumed by X4 or identical cross-process sector frames. TCP admission is
synthetic, X4 receives no motion setter, and this mode had not yet been run
natively at implementation time. It does not establish interest management, Windows, WAN or gameplay.

On 2026-11-16, `.local/authority-source-motion-saved-01` reported failure
`source or participant owner fault` and confirmed owned cleanup with no owned
processes remaining. Both logs record load requested, the expected marker and
pause; the client records `RUNNING`, but no `BUFFERED` marker. The source logs
`binding`, `attaching`, `await_go`, `observing`, then at game time 3.22 the X4
error `ConvertIDTo64Bit(): invalid id` followed by `AUTH_SOURCE_SINGLE ERROR
sampler tick sampler_tick`. There is no separate persisted trace proving the
registration response, a TCP motion receipt or the precise failing conversion
call.

The saved bootstrap hands an exact uint64 cdata to the source sampler; the
saved descriptor reader previously passed that value directly to
`ConvertIDTo64Bit`, whereas X4's conversion can require a Lua component
reference. This is a concrete code-level explanation consistent with the log,
but the actual failing call and native value type were not recorded. The
saved-only reader now reconstructs a local Lua reference, verifies any numeric
or cdata value without rounding, and requires the converted uint64 to equal the
original before reading. A fake X4 test rejects uint64 cdata as a Lua reference
and checks an opaque userdata with an exact value above 2^53 plus incorrect
roundtrips. The following run used this change, although it cannot isolate the
precise cause of the earlier failure.


On 2026-11-16, the fresh `.local/authority-source-motion-saved-02` run
reported success for one saved registry index, 1318, in
`cluster_115_sector001_macro`. Both X4 logs record load requested, the
expected marker inspection and pause. The source log then records `binding`,
`attaching`, `await_go` and `observing`; the client log records `RUNNING`
followed by `BUFFERED 1318 1 cluster_115_sector001_macro 3.226889243`. The
client marker records the source game-time field, not a synchronized
cross-process timestamp. These log lines alone do not show the UDP registration
or a TCP receipt.

The saved result reports a locally registered saved baseline, one sample and
a client bind/buffer confirmation. The sample has source game time
`3.226889243`, position `(-131815.453125, 1456.1622314453125,
-44962.0703125)` and unknown velocity (`null`). The reviewed worker and owner
code make the correlated source registration, TCP receipt and client-local
MD/FFI binding prerequisites for the reported result; the retained artifacts
do not include a packet trace or separate raw worker JSON. The result reports
no requested ship creation, no pose application, confirmed owned cleanup and
no remaining owned processes. The client buffer is hold-only.

This bounded result covers one existing saved index, one client and one source
sample in two local Linux X4 processes. It does not prove exact X4 save-file
consumption, cross-process actor or sector-frame identity, an atomically
unchanged source job state, speed, movement application, continuous
synchronization, interest management, persistence, combat, trade, boarding,
Windows or Internet operation. TCP admission and checkpoint proof in the
network coordinator are synthetic. The successful rerun is consistent with
the conversion fix; it does not establish which exact conversion failed in
the previous run.

### Experimental source-stop protocol

The Lua source-motion IPC can opt into a correlated `STOP`/`STOPPED` exchange
by supplying a synchronous stop callback. The callback contract requires the
owner to close its idle saved-registry bootstrap, sampler and event router
before returning success. The Python source IPC requires `stop_enabled=True`
for `stop_remote()` and refuses ordinary close until that remote stop succeeds.
A missing, stale or otherwise invalid reply faults the host. The X4-side UDP
socket stays bound until process cleanup so the supervisor can still check its
peer after `STOPPED`.

Offline Lua and real loopback UDP/Python tests exercise the wire sequence with
a simulated shutdown callback; they do not show an actual X4 bootstrap,
sampler or event router being stopped. The additive X4 source owner and its
shutdown callback are not integrated into the recovery supervisor. The outer
supervisor must fence the world and require successful remote stop before any
pause, save or disconnect. This protocol does not establish historical ship
identity, client application or multiplayer gameplay.
`STOPPED` alone does not prove that the event router stays fault-free after the
receipt. The eventual owner must continue guarding its session and error log,
and fence the session if a late event or any shutdown uncertainty occurs. Until
the real X4 shutdown callback and router are implemented and verified, this
STOP path is not a demonstrated basis for releasing a world pause or save.

A separate offline `source_motion_shutdown.lua` gate now requires an idle
bootstrap, ready sampler and caller-confirmed quiescence before closing both.
It seals the event route and faults late or reentrant events. This gate is not
installed in an X4 session: a future owner must actually route the unique MD
event through it and keep checking its status and error log after stop. An
in-flight saved-baseline bootstrap can no longer be closed as if it completed.

The opt-in recovered-source installer adds a source-only owner to an existing
recovery update loop. It binds the provided epoch and count to that loop's
registry configuration, checks the private save path, and uses one descriptor
event route and a separate UDP context. Offline tests use simulated X4 state;
this installer is not connected to the recovery supervisor or proven in X4.
The future supervisor must establish checkpoint and mapping provenance, protect
and redact the configuration, bind the UDP peer to its process, monitor
`AUTH_RECOVERED_SOURCE ERROR` through cleanup, and fence pause/save until STOP
and subsequent checks succeed. The additional MD script also requires an
explicit provenance decision before any resulting checkpoint is reused.

The local UDP library exposes a nonblocking `pending()` check so the source can
reject queued empty or oversized datagrams before and after STOP. This check is
a point-in-time observation, not a guarantee against future arrivals. The C
implementation has not been tested under Windows.

An explicit running-source bind variant now checks the same world, participant
and process/socket identities across the handoff; the existing paused-source
variant remains the default. A private guard-reader mode performs the full
witness-source validation before READY and supports correlated CHECK and STOP
requests. Its helper cleanup uses a verified pidfd and requires exclusive
ownership of the process's descriptor table. These pieces are not yet wired
into the recovery supervisor. Their timing and sustained throughput with a
large native save have not been measured.

`authority_registry_motion_candidate.lua` and its MD counterpart prepare a
bounded read-only search for a single saved-registry index in the live source.
They reject player-related ships and require consistent registry, operational,
sector and docking observations. This is only a point-in-time candidate: it
does not prove motion, reserve the ship, or replace the source bootstrap's
checks. The selector is not installed in the supervisor or verified in X4;
the current diagnostic still requires an explicit index.
