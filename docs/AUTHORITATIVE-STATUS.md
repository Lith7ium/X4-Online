# Authoritative-server experiment status

Snapshot: 2026-11-15. This branch is **not yet playable multiplayer**. The
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
* One running X4 process repeatedly read two registered ships in different
  sectors and observed their positions change. The observed rates were derived
  from position samples, not native velocity readback.
* Two isolated Linux X4 processes transferred a marked checkpoint locally,
  accepted a trusted client load claim over TCP, and confirmed resume and pause
  through TCP participant control. A second join was simulated. Another run
  loaded a marked checkpoint in a fresh server process and wrote a fresh
  confirmed checkpoint after a synthetic join. Neither run tested gameplay.
* In a separate two-X4 loopback run, the last control connection closed, after
  which the server paused and wrote a fresh marked checkpoint. The client game
  itself stayed open until cleanup; this did not test an actual game logout or
  a restart from that particular checkpoint.

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
[two-sector source read](../tools/dev/AUTHORITY-MULTI-SECTOR-READ.md),
[marked admission](AUTHORITY-TRUSTED-MARKED-LIVE.md),
[native TCP control](AUTHORITY-TCP-NATIVE-EXPERIMENT.md),
[recovered-world bridge](../tools/dev/AUTHORITY-RECOVERY-BRIDGE.md),
and [experimental local host](AUTHORITY-EXPERIMENTAL-LOCAL-HOST.md).
