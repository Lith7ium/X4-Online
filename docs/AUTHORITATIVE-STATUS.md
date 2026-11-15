# Authoritative-server experiment status

Snapshot: 2026-11-16. This branch is **not yet playable multiplayer**. The
target remains a persistent server-managed X4 universe with a Linux host who
also plays and a Windows player connecting directly over the Internet. Both
players share a company and account, can occupy different sectors, and should
eventually trade, fight, board and command ships. The simulation may pause
when nobody is connected and during joins. See the detailed experiment notes
for evidence and restrictions.

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

The main remaining work includes connecting the real X4 participant to network
control, resolving sector and object identity on each client, continuously
replicating ships and appropriate velocity, handling independent NPC simulation
and high-attention authority, and preserving client-originated gameplay effects
before saves. Combat, trading, boarding, cross-platform Internet operation and
the complete persistent shared-world scenario require actual end-to-end tests.

Detailed results: [census read](../tools/dev/AUTHORITY-CENSUS-RUNTIME-READ.md),
[saved-registry job attach](../tools/dev/AUTHORITY-JOB-ATTACH.md),
[local job descriptor](../tools/dev/AUTHORITY-JOB-DESCRIPTOR-PROBE.md),
[two-sector source read](../tools/dev/AUTHORITY-MULTI-SECTOR-READ.md),
[sector lookup calibration](../tools/dev/AUTHORITY-SECTOR-FIND-CALIBRATION.md),
[two-profile fingerprints](../tools/dev/AUTHORITY-SECTOR-FINGERPRINT.md),
[marked admission](AUTHORITY-TRUSTED-MARKED-LIVE.md),
[native TCP control](AUTHORITY-TCP-NATIVE-EXPERIMENT.md),
[TCP departure recovery](AUTHORITY-TCP-RECOVERY-EXPERIMENT.md),
[recovery with TCP client](AUTHORITY-RECOVERY-TCP-JOIN-EXPERIMENT.md),
[recovered-world bridge](../tools/dev/AUTHORITY-RECOVERY-BRIDGE.md),
and [experimental local host](AUTHORITY-EXPERIMENTAL-LOCAL-HOST.md).
