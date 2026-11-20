# Ship lifetime identity: experimental design

Status: **design only**. The user approved trying a persistent, increasing
lifetime number per ship identity. The proposed protocol, save representation,
migration and recovery rules below still need implementation and validation.
This decision does not establish complete ship coverage or playable multiplayer.

## Pending decision: checkpoint availability

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

This proposal changes checkpoint admission and therefore awaits the user's
decision before implementation. First native validation would examine how the
retained missing references resolve after load, whether a saved availability
record survives reload without table-key collapse, and whether available,
unavailable and explicitly closed entries remain distinguishable. It must not
assume that all seven disappeared by the same mechanism or remove their ship
class from coverage. The exact MD representation, event coverage, client
visibility behavior and migration are not yet settled.

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
