# Authoritative X4 investigation: initial assessment

Status: initial prototype and assessment, 15 November 2026. Native read-only
scanner experiments failed before a valid scan receipt; no native
authority correction experiment has been run. The branch is isolated and based
on public commit `b80712b39963c179dcdc2d99541cf9a25dacf7de`.

In a later read-only Linux experiment, two local X4 instances each returned the
same recorded pose for one known fixture at tick 30. The fleet scans in that run
still failed on a non-operational entry. This does not establish synchronization.
Another isolated Linux/Linux run transferred one fixture's read-only position
through a localhost UDP process between two X4 instances. Its validator matched
103 received samples against 150 logged source samples; the sampled coordinates
were stationary. The overall run still failed its independent fleet scan, and
does not establish moving-ship synchronization or Internet/Windows operation.
A subsequent isolated 360-tick Linux/Linux run sent and received positions for
the same fixture after a test-only movement order. The receiver logged 232
matching samples and a 1,284 m displacement. No pose was applied in the guest,
no velocity was transmitted, and the fleet scans still failed; this remains an
overall failed test, not a multiplayer or smooth-motion acceptance.
The non-operational entry was identified in the disposable snapshot as a
drifting ship wreck. A guarded read in two Linux instances matched an independent
snapshot/controller calculation to about 1.5 mm for that one object. This does
not identify other non-operational entries or prove a complete scan. A later
A later 360-tick Linux/Linux run independently matched 2,661 received samples
covering each of twelve enrolled fixtures, including one moved fixture. That
read-only local transport diagnostic passed; no guest poses or velocities were
applied. The overall run failed because the strict census failed and the
separate inventory encountered the same entry in two faction lists. The meaning
of that duplicate remains under investigation. Inventory diagnostics retain
unresolved entries and do not claim complete universe coverage.

## Question

Can one running X4 instance own a persistent universe while other X4 instances
present it and submit player actions, without requiring identical simulation of
the entire universe? A network relay by itself is not such a server. The
candidate server is initially a full X4 instance; headless operation, Linux and
Windows interoperability, and an eventual 4–6-player session remain unproven.
The owner's first target is to host the X4 server and play on the same Linux PC
while a friend on Windows connects directly over the Internet, without a VPN or
virtual LAN. The current local-only transport tests do not meet that target.
Players must be able to play simultaneously in different sectors anywhere in
the same universe and session; sharing a sector is not a prerequisite. This
requires concurrent, independently located high-attention regions, while the
server keeps their consequences in one shared world. The actual mapping of
those regions to X4 engine state and the reconciliation of their results remain
unproven. A successful local fixture exchange does not establish this behavior.

The requested model puts background/low-attention simulation on the server and
delegates high-attention results to a client. The server accepts results rather
than requiring anti-cheat enforcement. Where players' regions overlap, the
owner approved an initial single client writer per overlapping region; the
prototype currently models assignment per ship, and handoff must fence the old
writer. The owner also approved a full X4 instance as the initial server. X4
attention is not a simple sector-wide Boolean: existing analysis distinguishes camera-relative
object attention and player-relative zone attention. How to delegate its actual
engine state is still an open native question.

The world runs while at least one player participates. On the last departure,
the server must stop simulation and commit a usable save; the first returning
player loads a matching server checkpoint and the world resumes. For a join
while others play, pause the shared simulation, save and transfer the current
checkpoint, wait for the new client to finish loading, then resume together. A
network connection alone does not prove that the client has loaded the save or
is ready to participate. Server restart must recover a verified save and the
associated identity/authority metadata. None of these engine operations is
established by the prototype coordinator.

Ship positions are the first scope; trade and combat follow later. Spacesuits
and dropped cargo are deferred; missions currently have lower priority.
Synchronizing positions alone does not imply
the other game systems already work.
The owner reports that prior LAN experiments reduced stuttering for player and
NPC ships by sharing velocity as well as position. Position replication must
therefore account for velocity and smooth motion between updates. The earlier
implementation needs to be adapted and validated before claiming that it works
in this branch or choosing its interpolation/extrapolation behavior.
The earlier LAN prototype contains time-buffered interpolation and bounded
extrapolation using both linear and angular rates inferred from consecutive
poses. It has player-ship velocity application guarded by flight state; its NPC
path predicted pose rather than setting native NPC velocity. One bounded Linux
setter experiment used a synthetic counterpart and aligned parent frames; it did
not establish the coordinate conversion for rotated parents. An older Windows
playtest report still noted jumps at high speed and some NPCs showing zero
speed. Later smoothing changes have not been established in this branch. Actual
sampling age, per-ship update cadence, frame transitions and Windows/Internet
behavior need independent validation.
The shared-world acceptance goal also requires players to fight together and
against each other, attack NPC ships, trade, board ships, and command their
company's ships, including while players are in different sectors. These are
requirements, not capabilities established by the current prototype. Player
versus player combat and boarding under one shared player faction need explicit
engine investigation; no implementation semantics have been decided yet.
All participants initially share one player faction and one company account;
individual player factions and separate player accounts are later features.
NPC factions remain part of the simulated world and the ship census. The
shared account is a requirement, not implemented or validated synchronization.

The first full development check ran 3,020 tests: one diagnostic-classification
test failed and 56 tests were skipped because platform-specific executables,
native libraries or other prerequisites were unavailable. The classification
was fixed and its complete 32-test module subsequently passed; the new authority
tests also passed independently. The complete suite has not been rerun after
that fix and remains incomplete, including Windows and cross-platform evidence.
A targeted Linux gate module then ran 55 tests with the installed pinned Linux
executable; 53 passed and two Windows-executable checks were skipped.

The existing Linux/Linux 1,800-frame run recorded matching guest input and
player-body samples but NPC drift at tick 1227 and a WORLD motion digest
difference at tick 1319. Its separate lifecycle collection exceeded the 32 MiB
validator limit, so that run is not an overall PASS. See
`docs/LINUX-VALIDATION.md`. The drift makes strict whole-world determinism a
substantial engineering risk; it does not establish that authority is viable.

## Useful foundations and unresolved boundary

The existing native player input, identity, rendering, snapshot and disposable
launch tooling are candidates for reuse after their lockstep assumptions have
been reviewed. `gate_player_physics_network.h` in particular coordinates two
records and an admitted simulation update; it is not a server correction API.
The current barrier/input relay is not an authoritative universe.

Existing save-transfer work can inform a new join flow. The older seed protocol
(`x4lan/seed.py`) has a documented local Linux
save/transfer/reload test, while its host and guest experiments used sequential
native runs with synthetic counterparts. The current `joinfiles.py` and
`hotjoin.py` provide hashed, resumable transfers for the lockstep path and have
one-PC evidence. They do not establish an authoritative Windows/Linux session
or a complete persistent world. They should be adapted rather than silently
treated as an already integrated solution.

The older `x4-universe-authority` prototype contains baseline transfers,
authority/lease sequencing and guarded pose application. Its native seed
report describes free original ships converging in a bounded synthetic-host
replay, while docked/stored children changed state locally after
`ActivateObject(false)` and the overall runs failed. A later guarded run ended
with a 305 m stored-child error. The prototype does not establish suppression of
all guest AI, physics, docking, damage, production or mission effects. Its guest
scan acts on multiple unprotected ships and must not be reused as a single-object
control. Its old test harness writes to the installed extension and an existing
test profile; it must not be run for this investigation. Source and evidence:
`extension/x4_lan_lab/ui/universe_game.lua`,
`reports/NATIVE-SEED-OBJECTS.txt` and `dev/native_world_test.py` in the older
prototype. They are historical references, not the code of this branch.

An object's saved reference may identify an enrolled object across a particular
snapshot reload; a process-local pointer is not a network identity. A real
lifecycle protocol still needs explicit authority epochs, stable IDs and
generations, authenticated ownership, removal, recreation and recovery.

## First native experiment: proposed contract

Build a default-off experiment in the current isolated Linux harness. Use a
single enrolled, free, undocked, unoccupied fixture ship in a disposable
snapshot and one known parent sector. Never act on a general ship enumeration.
Reject missing or changed identity, parent, fixture status or player ownership;
reject docking, storage and unknown state. Capture the pinned executable hash,
bundle/config hashes and bounded evidence for all phases. Existing launcher
preflight, private profiles and owned-process cleanup remain mandatory.

1. Record position, rotation, linear and angular velocity, parent, identity and
   relevant object status before each action. In a two-instance run, prove both
   peers refer to the intended saved fixture without equating native pointers.
2. In the guest, create a documented 100 m position offset in the same sector.
   Verify the actual offset is between 99 m and 101 m. A no-correction control
   must first show the perturbation and its subsequent observations. Abort if
   the required writer or trustworthy readback is not available.
3. Deliver an explicitly labelled authority pose from the host, or a recorded
   synthetic source in an initial primitive test. Apply it only to the enrolled
   guest object. Capture immediate and post-simulation readbacks and at least
   300 consecutive simulation ticks after the initial correction. First perform
   this hold with no further pose writes; a separate repeated-write run may
   measure correction frequency but cannot prove suppression. Compare against
   authority samples at proven corresponding simulation times, not merely
   against setter arguments. If time alignment cannot be established, use a
   stationary synthetic reference and verify its motion and timing instead.
4. Run a control matrix with deactivation on/off and correction on/off, plus an
   undisturbed fixture. Fix the same intervention order and timing in each run.
   Include a controlled local movement stimulus and measure its effect without
   correction writes; otherwise an inactive object cannot establish suppression.
   Record actual motion and native status; `ActivateObject(false)` is not
   evidence that all simulation or consequences stopped. Exercise existing
   player control as an independent, measured check during the observation.
5. Require the final and every measured hold-period position error to be at most
   0.1 m, with identical parent and valid fixture identity. Missing samples,
   an unverified writer, unmeasured player control, unexpected lifecycle or
   inconsistent run conditions make the result FAIL or INCONCLUSIVE, not PASS.
   Report rotation and velocities separately; a pose setter does not prove a
   velocity correction or full motion or state equality. If the fixture moves,
   sample and compare corresponding host ticks rather than a stationary target.

The no-correction and deactivation comparisons determine whether observed
correction persists and whether this particular local object still competes with
the authority. Even a pass establishes only the measured object, fields and
conditions. A synthetic authority source does not prove transport, independent
server operation or reconnection. Packet loss, duplicates, old epochs,
ownership changes, object removal/recreation and reconnect require separate
protocol tests and later native evidence. Docking and effects such as damage,
loot, trading and mission rewards require their own acceptance boundaries.

## Next work

Review actual safe sector-position and deactivation calls and their readbacks in
the current Linux process. Design fixture enrollment, phase timing, independent
input observation and a strict evidence validator before enabling any writer.
If a safe writer or a meaningful suppression comparison cannot be established,
record the precise limitation rather than claiming the native test succeeded.
Do not merge main, publish, touch normal profiles or modify the installed game.
