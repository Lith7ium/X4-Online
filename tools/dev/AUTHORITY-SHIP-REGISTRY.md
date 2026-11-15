# Experimental MD ship-reference registry

`authority_ship_registry.xml` is a default-off MD script for an isolated X4
experiment, not an installed extension or a production protocol. The local X4
instance designated server supplies real, currently operational ship objects;
the script stores their MD references. A server-chosen, unique nonempty epoch
and a monotonically allocated integer together name a registry entry. The epoch
must be created and checked by the caller; the MD script does not authenticate
it or a client. Never use a local runtime object ID as a network identity.

Install the XML only in a disposable experiment overlay. Send events to screen
`X4AuthorityShipRegistry` using `AddUITriggeredEvent` and register handlers for
the event names below. Wait for each response before issuing the next request:
concurrent request correlation and delivery ordering are not established.

* `Initialize({epoch=...})` returns `Initialized(epoch)`. Send this exactly
  once for a fresh test world, with a validated unique string. The non-instanced
  state cue persists, and it cannot reset itself to a new epoch.
* `Status({})` emits `Epoch(epoch)` followed by `Count(last)`, or
  `Uninitialized` or `Faulted`. Count is the highest issued integer, including entries that
  cannot currently be resolved; it is not an operational-ship count.
* `Enroll({epoch=..., ship=...})` accepts an X4-local object reference and emits
  `Enrolled(index)` or `Refused`. The reverse table keys are object references,
  not names, macros or process-local IDs. Each request must supply the exact
  saved epoch. An existing mapping is checked
  against the forward mapping before it is returned.
* `Resolve({epoch=..., index=...})` emits `Actor(object)` or `Unavailable` for a missing,
  non-operational, non-ship, wrong epoch, or out-of-range reference. Unavailable does not
  establish destruction; no deletion or reuse operation is implemented. A valid
  reference must also pass the reverse check.

An inventory source can pass each candidate local object to `Enroll`, await the
answer, and retain the returned epoch/index with its subsequent observations.
The diagnostic fleet scanner is a candidate source, not a proved complete,
atomic inventory. Additional discovery and reconciliation are needed as ships
appear, disappear or change context. A remote instance can resolve a registered
entry only after loading the checkpoint containing the register. This does not
bind independently created ships after a checkpoint or synchronize their state.

The implementation uses object-keyed tables instead of a full scan for each
registration; no complexity or performance guarantee follows. One isolated
Linux/Linux run enrolled and re-enrolled 10,054 operational candidates, saved
them, then resolved and re-enrolled all of them in a second X4 instance. The
checkpoint's forward and reverse tables were independently checked against
10,054 distinct saved ship components, and their per-index macros matched both
processes' observations. The inventory saw 140 sectors and rejected 49 other
distinct objects as unconfirmed. This is evidence for this checkpoint and the
observed candidates, not complete universe coverage or an independent binding
of each client runtime object to its saved component. Destruction, creation
after checkpoint, and index invalidation remain unverified. No clients were
admitted and no gameplay was tested.

An inconsistent reverse entry or write readback latches a fault. Allocation
uses a separate saved counter rather than the number of currently present
entries, so intended no-reuse does not rely on table compaction; destructive
lifecycle behavior requires native verification. This experimental code must
not be used as a production gameplay adapter.

## Saved sector ancestry

An additional read-only check of the archived `authority-registry-census-01`
confirmed checkpoint reports 10,054 distinct registered saved ships with
sector and zone ancestors. Their ancestors contain 140 distinct saved sector
component IDs. Two registered ships lie below a docking bay and have a
non-zone nearest component parent, showing why direct-parent-is-zone is not a
general rule. The checkpoint, archived server save and archived client save
had identical SHA-256 values when checked:
`64a233ac6a85194b8276212709e78a6c48bbcc0f73c19842622aa098f1408cb8`.

The check uses the existing checkpoint verifier, which verifies gzip contents,
the checkpoint digest, the bijective forward/reverse tables, registered ship
components and per-index macro rows from the server and client logs. To repeat
the analysis against a retained local archive, supply its epoch from the unique
`AUTH_REGISTRY save EPOCH` log line:

```sh
python tools/dev/authority_registry_save_evidence.py \
  --store .local/authority-registry-census-01/checkpoints \
  --expected-epoch EPOCH_FROM_SERVER_LOG --expected-count 10054 \
  --server-log .local/authority-registry-census-01/server/case/home/.config/EgoSoft/X4/45841/engine-output.log \
  --client-log .local/authority-registry-census-01/client/case/home/.config/EgoSoft/X4/45841/engine-output.log \
  --sector-parents
```

The checker reads the confirmed checkpoint; comparing the two archived save
files to the reported checkpoint hash is a separate filesystem check. These
are relationships in the stored XML, not an independent runtime binding of
client objects to those components. The logs do not contain per-index sector
identities. This does not prove that either X4 process consumed the exact file
bytes, sector completeness, dynamic zone identity, position/velocity
replication, or operation in different sectors during gameplay.

## Pinned census archive check

`authority_census_archive_provenance.py` checks this specific recorded census
checkpoint without loading X4 or modifying the archive. It requires equal
`CURRENT` and `CONFIRMED` pointers, the recorded checkpoint ID, compressed
SHA-256 and size, the marker in the saved `Store` cue, and the recorded registry
epoch. The existing structural verifier checks all 10,054 forward and reverse
entries against distinct saved ship components. The checker does not reread
the two historical process logs or compare their per-index macro observations;
the separate command above does that.

File and path identities are sampled around the checks and symlinks are
rejected. Every marker and registry parsing pass checks the compressed digest.
These checks detect ordinary changes but do not provide atomic filesystem
fencing or prove which bytes an X4 process loaded. This legacy checkpoint's
marker is verified in the save, not bound in the version-1 manifest. It does
not establish runtime object identity, complete universe coverage, dynamic
ships, or multiplayer. Run only when this pinned archive needs verification;
the streaming XML checks reread the large save several times.

```sh
python tools/dev/authority_census_archive_provenance.py
```

## Saved sector macro names

`authority_sector_macro_save_evidence.py` checks the same pinned census
checkpoint without launching X4. It requires matching confirmed/current
pointers and the recorded checkpoint ID, size and compressed SHA-256, and it
streams the saved XML through the existing digest-checking parser. It counts
sector components under the saved universe, rejecting missing or duplicate
component IDs and missing or duplicate macro names. Macro comparison uses
case-folding conservatively. Path/file fingerprints are sampled around the
check; they are not an atomic or adversarial filesystem fence.

One read-only verification on 15 November 2026 found **152 saved sectors, 152
distinct saved sector IDs, and 152 distinct case-folded sector macro names** in
the pinned checkpoint. The earlier ship-ancestry analysis found registered
ships in 140 saved sectors. These two observations do not map local runtime
handles to saved components, establish cross-process sector frames or prove
that sector macro names are unique in other worlds, mods, or dynamically
created sectors. They do not prove which bytes X4 loaded. Do not use the
result by itself as a multiplayer frame-identity contract.

```sh
python3 tools/dev/authority_sector_macro_save_evidence.py
python3 -m unittest tests.test_authority_sector_macro_save_evidence
```
