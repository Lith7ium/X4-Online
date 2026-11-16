# Authoritative-server experiment status

Snapshot: 2026-11-16. This branch is **not yet playable multiplayer**. The
target remains a persistent server-managed X4 universe with a Linux host who
also plays and a Windows player connecting directly over the Internet. Both
players share a company and account, can occupy different sectors, and should
eventually trade, fight, board and command ships. The simulation may pause
when nobody is connected and during joins. See the detailed experiment notes
for evidence and restrictions.

An offline result for the pinned census save groups all 10,054 registry
indices exactly once by saved sector ancestry: 140 of 152 saved sectors have
at least one witness. Its reported checkpoint, digest and registry epoch match
the pinned provenance values. This is saved-state evidence, not a runtime
sector binding or proof of a shared coordinate frame. See the
[census witness notes](../tools/dev/AUTHORITY-CENSUS-SECTOR-WITNESS.md).

Native Linux evidence so far:

* One paused X4 process read all 10,054 indices in a recorded registry: 10,052
  finite positions in 140 local sectors, with two docked or internally stored
  entries excluded from position reads. This is one saved registry, not proof
  of complete universe coverage, live replication or cross-client identity.
* One isolated Linux X4 process attached a job observer to the saved 10,054
  entry registry while paused, resumed, and reported 23 locally acknowledged
  activations with new registry indices before pausing again. First registry
  allocation does not prove ship construction or delivery, and this is not
  complete event coverage or replication.
* A separate isolated run attached to that registry and sampled a non-atomic
  macro, owner, sector macro and position for its first newly registered job
  actor. No client received or recreated the ship.
* One running X4 process repeatedly read two registered ships in different
  sectors and observed their positions change. The observed rates were derived
  from position samples, not native velocity readback.
* One paused isolated Linux X4 resolved two saved fixture sector macros with
  `find_sector`; each returned one local match agreeing with the stored local
  sector reference and FFI relationship checks. This calibrates those two
  sectors only, not universal uniqueness or cross-client identity.
* Two sequential isolated Linux profiles each read two saved ships in distinct
  sectors and reported ship codes/macros and sector macros matching their
  independently parsed checkpoint attributes. Local handle checks passed; this
  is bounded evidence for these two slots, not general identity or simultaneous
  multiplayer.
* One paused isolated Linux X4 process created and replayed two test ships in
  distinct sectors remote from the player. Registry/position readbacks and an
  argon faction-and-macro count were consistent with one new object per index.
  This is a local fixture, not network delivery or reconciliation; the requested
  coordinates are synthetic and collision-free placement is unproven.
* Two paused isolated Linux X4 processes completed a single synthetic
  index-3 ship descriptor transfer over localhost TCP, with guarded local
  creation, replay and inspection in a sector remote from each player. This
  is one fixture, not full ship-state synchronization, Windows/Internet or
  gameplay; the seed is a test input. The detailed record distinguishes the
  X4 log receipts from the coordinator's ACK and cleanup report.
* In a separate two-X4 Linux localhost diagnostic, the source registered one
  job activation at index 10055, paused, and reported its descriptor. The
  coordinator reports a saved sector witness verified locally in both
  processes before the TCP ACK. This does not prove ship birth, replica creation
  or a shared coordinate frame; log and coordinator evidence have different
  limits detailed in the diagnostic.
* A further isolated two-X4 Linux localhost run reported one newly registered
  job activation at index 10055, transferred its descriptor and completed a
  guarded approximate client creation and replay before the coordinator's TCP
  ACK. The local logs and coordinator result provide different parts of the
  evidence; there is no packet trace. The replica uses an artificial seed and
  approximate loadout. This is one paused fixture, not continuous ship-state
  synchronization, proven shared frames, Windows/Internet or gameplay.
* A later isolated two-X4 Linux run held one job event at the source while one
  approximate client replica was created and inspected. The coordinator
  reported a localhost TCP ACK before releasing the source event, and the
  server log recorded `SOURCE_ACKED` after the MD acknowledgement. The
  cross-process order rests on coordinator code and result, not a packet trace.
  The TCP receiver was a local supervisor callback, the seed and loadout were
  artificial, and one activation does not prove ship birth. This does not
  establish multiple clients, Windows/Internet or gameplay. An earlier attempt
  was refused before X4 launch due to an exact saved-script mismatch; a
  byte-identical save-era fixture preserved that provenance check.
* One isolated three-X4 Linux run held a single job activation at the source
  until two local client replicas were created and inspected. The source log
  records a partial acknowledgement followed by the final source
  acknowledgement; both client logs record their replica completion. The
  ordering of the two TCP acknowledgements relative to those events rests on
  coordinator code and result, without an independent packet trace. The TCP
  receivers were local supervisor callbacks. Both replicas used artificial
  seed 7183 and approximate loadouts; activation does not prove ship birth.
  This is not complete-universe synchronization, Windows, Internet or gameplay
  evidence. See [the three-X4 record](../tools/dev/AUTHORITY-CENSUS-REPLICA-TWO-CLIENTS.md).
* A separate paused single-X4 Linux experiment reported two sequential local
  creations in different census-witnessed sectors, followed by a replay of
  each. Its scenario log records the creates, replays and completion; the
  individual MD and FFI checks are prerequisites in the scenario code, not
  independently logged observations. Seed 7183, positions and loadouts were
  artificial. This is not a source event, TCP transfer, multi-client,
  cross-frame, Windows/Internet, gameplay or persistence test. See the
  [local multi-create record](../tools/dev/AUTHORITY-MULTI-CREATE-LIVE.md).
* A separate single-X4 Linux diagnostic resumed after an observed pause and
  logged one synthetic create in a census-witnessed sector while sampled game
  time advanced. The correlated MD and running-FFI checks are prerequisites in
  the owner code; their individual observations are not separately logged.
  Seed, position and loadout were artificial. Samples do not prove continuous
  running, and this is not a source/TCP, multiple-client, Windows/Internet,
  gameplay or persistence test. See the
  [running local-create record](../tools/dev/AUTHORITY-MULTI-CREATE-RUNNING.md).
* In an isolated player-seat calibration, an NPC with an observed pilot and
  started Patrol returned a valid assigned pilot while its control-post
  reservation lookup reported empty. The positive control failed before the
  two test ships' seats were assessed. This does not establish an empty or
  usable physical seat, player control, or the cause of the differing readings.
* A separate isolated read-only search for a positive seat-control candidate
  completed with an inconclusive outcome. The retained result does not identify
  which search or timeout path occurred and does not establish that no candidate
  exists or that a seat is free.
* One disposable Linux X4 process created a player-owned fixture, requested a
  teleport and reported two guarded matching local player-control readbacks
  while paused. This is a single local case, not demonstrated flight, a free
  seat, cross-client synchronization, Windows/Internet or gameplay.
* A separate disposable Linux X4 run confirmed local player-control readbacks,
  resumed the simulation, and passively sampled the same pose three times over
  about 0.075 seconds of advancing game time. No input was injected or save
  requested. This does not prove steering, continuous stillness, multiplayer,
  Windows or Internet operation.
* A separate default-off Linux X11 input helper has only synthetic and owned
  helper-process coverage. It has not been integrated with a flight harness or
  tested against an actual X server or X4; key release is not guaranteed under
  simultaneous hard failures, so private display cleanup remains essential.
* Two isolated Linux X4 processes transferred a marked checkpoint locally,
  accepted a trusted client load claim over TCP, and confirmed resume and pause
  through TCP participant control. A second join was simulated. Another run
  loaded a marked checkpoint in a fresh server process and wrote a fresh
  confirmed checkpoint after a synthetic join. Neither run tested gameplay.
* In a separate two-X4 loopback run, the last control connection closed, after
  which the server paused and wrote a fresh marked checkpoint. A later isolated
  Linux X4 process loaded that checkpoint, reported its saved marker and pause,
  and produced another confirmed checkpoint after a synthetic waiting join.
  The original client game stayed open until cleanup; neither run tested an
  actual game logout or gameplay after restart. Exact X4 file consumption and
  zero simulation before pause are not proven.
* A further isolated Linux/Linux loopback run loaded the latter checkpoint in
  a fresh server, created a new marked join checkpoint, and admitted one real
  second X4 using a cooperative TCP load claim. The harness confirmed native
  server/client resume and clean helper/process cleanup. Two saved fixture
  references were observed on the client. This is a bounded reconnect chain,
  not a real player logout, continued-session or gameplay test.

TCP load and participant control have also passed a bounded native Linux/Linux
loopback diagnostic. They are not yet connected to a playable client or public listener.
There is no demonstrated Windows or Internet session. The Linux native velocity
work in earlier LAN experiments provides useful prior evidence, but its
fixture-specific guards and reference-frame assumptions are not yet a general
NPC solution.

An isolated NPC constant-velocity experiment logged conversion errors for its
requested zero-vector expression. Its historical success flag only reflects
the harness checks; the setter's physical effect and release outcome remain
inconclusive. See [the diagnostic](../tools/dev/AUTHORITY-NPC-CONSTANTVEL.md).
An earlier fixture-velocity run likewise logged conversion and arithmetic-type
errors for its requested expressions. Its observed displacements remain useful
measurements, but the setter effect and units are inconclusive despite the
historical success flag. See [the fixture record](AUTHORITY-FIXTURE-VELOCITY-EXPERIMENT.md).

The main remaining work includes connecting the real X4 participant to network
control, resolving sector and object identity on each client, continuously
replicating ships and appropriate velocity, handling independent NPC simulation
and high-attention authority, and preserving client-originated gameplay effects
before saves. Combat, trading, boarding, cross-platform Internet operation and
the complete persistent shared-world scenario require actual end-to-end tests.

Detailed results: [census read](../tools/dev/AUTHORITY-CENSUS-RUNTIME-READ.md),
[saved-registry job attach](../tools/dev/AUTHORITY-JOB-ATTACH.md),
[local job descriptor](../tools/dev/AUTHORITY-JOB-DESCRIPTOR-PROBE.md),
[two-X4 census descriptor](../tools/dev/AUTHORITY-CENSUS-PAIR-READ.md),
[two-X4 census replica](../tools/dev/AUTHORITY-CENSUS-REPLICA-PAIR.md),
[player-seat experiment](../tools/dev/AUTHORITY-PLAYER-SEAT-EXPERIMENT.md),
[positive-seat search](../tools/dev/AUTHORITY-POSITIVE-SEAT-SEARCH.md),
[local player-control probe](../tools/dev/AUTHORITY-PLAYER-CONTROL-ONCE.md),
[player-flight observer preparation](../tools/dev/AUTHORITY-PLAYER-FLIGHT-OBSERVER.md),
[passive native flight observation](../tools/dev/AUTHORITY-PLAYER-FLIGHT-LIVE.md),
[private X11 input helper preparation](../tools/dev/AUTHORITY-X11-PRIVATE-KEY-PULSE.md),
[two-sector source read](../tools/dev/AUTHORITY-MULTI-SECTOR-READ.md),
[sector lookup calibration](../tools/dev/AUTHORITY-SECTOR-FIND-CALIBRATION.md),
[two-sector local creation](../tools/dev/AUTHORITY-SECTOR-CREATE-PREPARATION.md),
[two-X4 local ship transfer](../tools/dev/AUTHORITY-SECTOR-PAIR-TRANSFER.md),
[two-profile fingerprints](../tools/dev/AUTHORITY-SECTOR-FINGERPRINT.md),
[marked admission](AUTHORITY-TRUSTED-MARKED-LIVE.md),
[native TCP control](AUTHORITY-TCP-NATIVE-EXPERIMENT.md),
[TCP departure recovery](AUTHORITY-TCP-RECOVERY-EXPERIMENT.md),
[recovery with TCP client](AUTHORITY-RECOVERY-TCP-JOIN-EXPERIMENT.md),
[recovered-world bridge](../tools/dev/AUTHORITY-RECOVERY-BRIDGE.md),
and [experimental local host](AUTHORITY-EXPERIMENTAL-LOCAL-HOST.md).
