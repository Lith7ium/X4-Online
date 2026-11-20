# Ship lifetime identity: experimental design

Status: **design only**. The user approved trying a persistent, increasing
lifetime number per ship identity. The proposed protocol, save representation,
migration and recovery rules below still need implementation and validation.
This decision does not establish complete ship coverage or playable multiplayer.

## Approved experiment: checkpoint availability

Native04 completed its one-ship motion experiment, then failed the post-motion
checkpoint check: seven of 10,082 issued registry entries had no component
definition in the save. The previous confirmed save contains all seven as
`ship_xs` police ships. The candidate retains their forward and reverse
component references; reference persistence does not establish a live object.
The strict verifier still rejects this candidate, and the previous confirmed
checkpoint remains available. See the
[native04 evidence](../reports/AUTHORITY-MOTION-CLOCK-BASIS-20261118.md#native04-prepared-playback-completed-overall-registry-check-failed-2026-11-20).

The registry contract counts issued indices, including unresolved entries,
while the checkpoint verifier requires a saved ship component for every index.
The proposed next experiment is to separate **availability** from **destruction**:

- Retain issued identities and their lifetime metadata. Record an explicit
  unavailable state when a validated authoritative game-side observation cannot
  resolve an entry. A missing XML component alone must not produce this state.
- Allow an unavailable entry in a new checkpoint format only if the saved
  availability state and registry structure agree. Continue requiring component
  definitions for entries declared available. An unexplained missing component,
  contradictory observation, aliased reference or ambiguous saved state rejects
  the checkpoint. Existing checkpoints keep their current verification rules.
- An unavailable entry cannot supply a movement or command target. It is not
  an instruction to destroy a client's ship, close a lifetime or reuse an index.
  Returning availability needs a validated binding to the same lifetime; do not
  infer one from a reused engine handle, macro or name.
- Only a separately validated lifecycle operation may close a lifetime. The
  approved increasing lifetime number remains the protection against stale
  messages when an identity is subsequently rebound.

The user approved this availability experiment on 2026-11-20. Admission remains
unchanged until game-side observation and save/reload validation support a new
format; approval is not evidence that it works. First native validation examines how the
retained missing references resolve after load, whether a saved availability
record survives reload without table-key collapse, and whether available,
unavailable and explicitly closed entries remain distinguishable. It must not
assume that all seven disappeared by the same mechanism or remove their ship
class from coverage. The exact MD representation, event coverage, client
visibility behavior and migration are not yet settled.

The first implementation is a default-off diagnostic in
`tools/dev/authority_registry_availability_probe.{lua,xml}`. It observes up to
16 explicitly selected indices from a fixed issued-count snapshot and saves
five separate integer-flag tables: forward entry present, object exists, ship
class, operational, and reverse mapping matches. Seal closes capture; Inspect
reports saved and fresh flags without overwriting the saved observations.
The registry and game objects are read-only. The saved `faulted` field is
reserved: false does not prove Lua-owner success, which must be established
separately from correlated receipts.

`authority_registry_availability_saved.py` validates only the checkpoint bytes,
including digest, correlation, table separation and exact selected indices.
It does not decide availability or destruction and is not used by admission.
Five structural MD tests, eight saved-reader tests and the Lua owner test
passed; private synthetic adapter checks cover capture/save and inspect wiring.
These results do not establish native MD semantics or persistence. A private
single-process-at-a-time capture/save/restart experiment is prepared for the
seven missing entries plus control index 1318.

The first native capture/save completed. All seven missing entries returned
forward-present=true and object-exists=false; control 1318 returned all five
flags true. Class, operational and reverse checks are conditional on existence,
so their false values for missing objects are not independent lifecycle proof.
The initial offline read failed because native reference IDs are scoped by type
and Lua-supplied table indices were saved as integral `largefloat` keys. After
matching those observed encodings, all ten saved-reader tests passed and the
same retained save parsed successfully. No capture was repeated. The existing
strict registry verifier separately reports `incomplete table` on that save;
its registry shape and the pending reload must be examined before admission can
change. Private capture evidence: `.local/registry-availability-native-20261120-01`.

The continuation at `d8da5c08` loaded that same retained save in a fresh private
process. Saved and fresh flags matched for all eight indices. The outer run,
display release and owned-process cleanup passed; original checkpoints and
the diagnostic save were unchanged. No admission change followed this result.
Private reload evidence: `.local/registry-availability-native-20261120-02`.

Offline registry comparison explains the remaining strict rejection. The
resaved forward table still has all 10,082 integer indices, but the seven
unavailable component values are now `[0x0]`. They share one reverse key, pointing
to index 672, leaving 10,076 reverse rows. The control retains `[0x7a18a]` and its
matching reverse row. The previous candidate contained seven distinct nonzero
references even though their component definitions were missing. This is
evidence of saved reference loss and null-key collapse; it does not explain why
the objects became unavailable or establish their destruction.

### Next format proposal after native observation

Implementation proposal within the approved availability experiment; not
implemented in admission. Automatic rebinding or identity reuse is outside
this proposal and would need a separate decision:

- Keep an issued multiplayer identity even when X4 no longer supplies a usable
  object reference. Store its explicit availability independently of that
  reference and of the reverse lookup table.
- Require a complete, unique forward/reverse binding for entries declared
  available. The reverse lookup contains only validated usable objects;
  unavailable entries cannot contribute a shared null key or receive commands
  or motion updates.
- Do not reassign or revive an unavailable identity automatically. Its former
  X4 reference is not a recovery key after resave. Any future rebinding needs
  separate identity/lifetime evidence and an explicit transition.
- Use a distinct save format and reject incomplete availability coverage.
  Validate all issued entries in a full-register save/reload experiment before
  changing checkpoint admission. Old-format acceptance remains unchanged.

The eight-row experiment supports the storage mechanism, not complete ship
coverage, full-register performance, lifecycle transitions or client recovery.

### Full-register snapshot implementation

`tools/dev/authority_registry_availability_snapshot.{xml,lua}` implements a
separate, default-off format-2 snapshot. The caller pins the source epoch and
issued count. Capture visits every issued index in contiguous batches of at
most 64 and seals only after complete coverage. The availability table retains
every index; forward and reverse object tables contain available entries only.
An absent X4 object can be recorded as unavailable. An existing non-operational
object, wrong class, conflicting reverse binding or duplicate object faults the
capture instead. The source registry is never rewritten.

Inspect compares saved flags and current X4 bindings without updating the
snapshot. A saved unavailable entry cannot become available implicitly. The
separate `authority.registry_availability_evidence` reader checks saved flags,
counts, exact forward/reverse bindings and component definitions, using typed
reference IDs and X4's observed integral numeric-key encoding. Its result
describes saved bytes only; it is not a runtime or historical identity proof.

This snapshot has no command or motion consumer and is not wired into
checkpoint admission. Targeted synthetic checks cover the owner, saved-byte
reader and private adapter; full-register native save/reload validation is the
next step. All registered entries is a narrower claim than all universe ships.

## Existing identity

The experimental motion-v1 identity contains a registry `epoch`, a random
32-hex `generation` token and an `index`. Its generation is also used in the
source/job context; it is not an ordered lifetime number. The current sender
and receiver keep closed track entries as process-local tombstones, and their
bounded track tables can fill as lifetimes accumulate. The saved experimental
registry currently assigns increasing indices and keeps its own epoch and
object references. It has no persisted per-index lifetime counter.

Do not change the meaning or encoding of the v1 generation token. A v2
experiment needs an explicit version and a separate lifetime field; reject
unknown versions and malformed or incomplete identity data. Existing v1
experiments remain v1 unless explicitly migrated to a separately defined v2
path. No automatic inference of v2 state from a v1 message is safe.

## Proposed invariants

- A lifetime is identified by `(registry_epoch, ship_index, lifetime_number)`.
  The lifetime number is a positive exact integer, bounded to at most `2^53-1`
  for interoperable Lua/JSON handling. The authority owns its allocation.
- Retain a high-watermark and active/closed state per registered index in the
  authoritative saved state. A subsequent lifetime can be opened only after
  the previous lifetime is closed and must use exactly the next number.
  Detect exhaustion and fail closed; never wrap or silently reset a counter.
- Only an explicit, validated authority lifecycle operation may establish a
  lifetime and bind its object. A position update cannot create or reopen one.
  Senders and receivers reject stale, closed, unexpected or malformed lifetime
  identities before invoking game callbacks. Within the active lifetime, they
  independently reject stale motion sequence numbers.
- Reliably deliver the closing event to each relevant connected recipient, or
  fence the recipient's connection, before allowing that recipient to receive
  a subsequent lifetime for the same index. A position queue may replace an
  obsolete unsent position; it must not replace a lifecycle event.
- After closure is safely fenced, retire bulky active track and per-peer state
  while retaining the high-watermark. This bounds lifetime bookkeeping per
  registered index, not the total number of ship indices over world history.
- Changing sectors, map interest, connection, or high-attention owner does
  not by itself create a new physical ship lifetime. Authority handover needs
  its own current ownership lease and fencing: a lifetime number alone cannot
  reject an old owner that still refers to the same ship.

These are proposed correctness conditions, not claims about the existing
experimental v1 code. Exact lifecycle events, acknowledgement and client
re-entry procedures still require integration and game-side evidence.

## Checkpoints and restart

The saved counter, closed/active state and registry mapping must be verified as
one consistent checkpoint before it is offered or accepted for recovery. An
older save without the necessary fields must not silently become a proven v2
baseline. An explicit migration or fresh-world bootstrap needs its own
documented validation and rollback behavior.

A checkpoint can predate lifetime numbers sent after it was written. Restoring
that checkpoint alone therefore cannot reject every message from the abandoned
execution. The proposed recovery fence starts a new session epoch and requires
the receiver to validate it, together with the current connection incarnation,
before accepting lifecycle or motion data. Old session messages are rejected
even if a restored counter later reaches the same value. This requires proof
that no receive path bypasses the session fence. If a session must survive a
server restart instead, a separate durable allocation mechanism outside the
checkpoint would be needed; it has not been designed or approved here.

The current experimental registry and motion implementations also impose
separate 200,000-entry and 100,000-track limits. A per-index watermark removes
growth per reused lifetime but does not solve growth from ever-new indices,
dead object references, or eventual exhaustion. Those limits and safe registry
retirement require further design and measured whole-world evidence.

## Validation still needed

Exercise stale and reordered lifecycle/motion messages, partial sends,
disconnects, reconnects and multiple recipients; prove a stale owner is fenced
after handover; and check counter exhaustion, ambiguous saves and migration
failures. Test saving, restart and rollback across actual X4 processes before
claiming persistence. Finally verify cross-process ship binding, interest
changes, Windows and Internet behavior; local synthetic receipts do not prove
any of these.
