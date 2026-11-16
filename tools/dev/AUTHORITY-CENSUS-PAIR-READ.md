# Private two-X4 census job descriptor and witness diagnostic

This opt-in experiment is designed to connect two earlier bounded findings: a
saved 10,054-entry registry with a local job-activation descriptor, and a local
TCP exchange between two owned Linux X4 instances. It is not multiplayer. It
sends no Create request, transfers no X4 runtime handle, and writes no game
checkpoint. The archived `authority_identity_fixture.xml` still contains its
original Spawn cue; the new owner never requests it. That archived script is
byte-checked because it was present in the saved state.

The runner validates the pinned census archive once using its existing
confirmed-pointer, marker, digest and saved registry-bijection verifier. It
reads the pinned all-sector witness JSON once, requires its recorded SHA-256,
validates the full 152-sector/10,054-index structure, and keeps only immutable
eligible saved witness candidates in memory. The JSON pin establishes the
specific artifact bytes, not an independent proof that those bytes were derived
from the save. The source checkpoint is opened through a regular-file FD and
read once into two distinct, newly created private save slots. Both staged
files are separately rehashed and the source and archive fingerprints checked;
the save directories are mounted read-only into X4. Protected overlays,
staged saves, identities and archive are checked before each process launch,
during the diagnostic and after owned cleanup. This is sampled file/process
fencing, not protection from adversarial ABA changes or proof of what X4 read.

Both separate profiles must report their expected load and marker, and pause.
The sole load-update owner in each profile drives one census owner. The source
must attach the saved registry and a previously uninitialized job queue while
paused; the client separately checks its saved registry epoch, last index and
healthy tables without initializing a job queue. Only after both local READY
receipts and CHECK/CHECKED guards may the source resume. It observes the first
new registry index 10055, stops polling further events, pauses, and reads a
bounded descriptor from that same local actor. Re-activations of existing
indices are not new ships. An event not observed, queue overflow, lost actor,
missing saved sector or unavailable runtime witness cannot be treated as
success; the temporary profiles must be discarded.

If the source's bounded queue window closes with no newly allocated registry
entry, its owner pauses and emits a distinct `NO_EVENT` status. Only after a
further two-owner guard and final process, UDP and log checks is this reported
as `inconclusive_no_new_registry_entry`, with `success=false`. It covers both
zero observed activations and only reactivations of already registered actors;
it does not prove that the universe created no ships.

The coordinator selects one saved registry witness for the descriptor sector
that was saved outside a docking bay directly under a zone. Source and client
independently resolve the witness actor and require an exact one-sector local
lookup with matching sector/actor checks while paused. The source's descriptor
is then sent over one real loopback TCP connection by an exec-gated, pidfd-owned
helper. TCP ACK follows the client's correlated successful witness callback and
another guard. Job queue sequence and transport sequence remain separate. The
helper must be stopped and reaped before X4 processes or their lock are
released; uncertain cleanup retains the lock. Late UDP or log faults invalidate
success. Source game and client game state are not atomically sampled, and
CHECK/CHECKED and engine logs are point observations rather than continuous
proof of pause or identity.

An ACK describes that one client-local witness check only. Neither a sector
macro nor saved component reference alone proves an equivalent coordinate frame
across instances, an existing actor match, ship birth or successful creation.
Seed, velocity, pilot, orders, equipment, faction AI and client autonomous
spawns are not transferred or reconciled. This experiment does not prove queue
coverage, lossless delivery, Internet/Windows behavior, shared gameplay or a
persistent multiplayer world. Normal profiles and saves must never be used.

Offline tests use synthetic saved artifacts and fake X4 owners/processes plus
real local UDP/TCP and a gated helper. They do not start X4 or reread the large
census archive. Before a native run, the complete source/overlay/protocol and
cleanup path needs independent review; a failed or ambiguous diagnostic is not
retried against an already mutated profile.
