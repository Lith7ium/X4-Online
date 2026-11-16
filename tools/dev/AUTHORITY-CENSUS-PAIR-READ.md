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
census archive. The integration received independent review before the bounded
native run below; a failed or ambiguous diagnostic must not be retried against
an already mutated profile.

## Bounded native Linux/Linux run

The disposable `.local/authority-census-pair-01` result reports success,
confirmed owned cleanup and no remaining owned processes. It reports job
sequence 1 and newly allocated registry index 10055, with a descriptor for
`ship_gen_m_tugboat_01_a_macro`, faction `pioneers`, in
`cluster_115_sector001_macro`, at sector coordinates
(-132217.25, 6004.3818359375, 169081.453125). The selected saved-sector
witness was registry index 1318; the pinned witness artifact lists that index
under the same sector with a zone as its immediate saved component parent.
This is a job activation and new registry entry, not proof of ship birth.

Both X4 logs record load request, saved marker inspection, pause receipt and
local READY, followed by repeated CHECKED receipts. The source log records
DESCRIPTOR then WITNESS_OK; the client log records WITNESS_OK. The source's
logged game time advanced from about 3.04 to 13.08 seconds, then remained at
13.08 through its descriptor and witness receipts; the client's logged time
remained about 3.04. According to the reviewed coordinator and its successful
result, the source witness preceded one localhost TCP descriptor exchange,
the client witness preceded its TCP ACK, and helper and X4 cleanup were
confirmed. Those cross-process steps and descriptor values are reported by the
coordinator, not independently established by a saved TCP packet trace; the
individual X4 log labels do not contain the descriptor or actor IDs.

The pinned source save and both private staged copies have compressed SHA-256
`64a233ac6a85194b8276212709e78a6c48bbcc0f73c19842622aa098f1408cb8`;
the existing witness JSON hashes to
`006b07a39be4cff6a3fac7555b26d40ffe834594304c231dd659b23bfdc85349`.
The recorded private Lua and MD scripts match the reviewed sources or expected
module-export transformations, and saved-state MD scripts match the archive.
Matching file hashes do not prove which bytes X4 consumed, and the witness
artifact hash does not independently establish its derivation from the save.

This single diagnostic requests neither replica creation nor a game save. It
does not prove matching runtime coordinate frames, complete ship-state or
universe synchronization, event coverage, Windows/Internet operation,
combat, trade, boarding or playable shared-world persistence.
