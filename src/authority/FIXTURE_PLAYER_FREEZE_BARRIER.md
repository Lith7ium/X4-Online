# Fixture player freeze/drain barrier: offline design

`lua/fixture_player_freeze_barrier.lua` is default-off. It does not register
an X4 event or update owner, read a socket, send UDP, pause X4 or connect to
the current client session. Its callbacks and synthetic tests describe one
possible bounded coordination contract; an actual integration is still open.

`freeze(id)` stops the caller's scheduling of new descriptor reads, then
enters `draining` with a monotonic deadline. The existing owner continues to
route its already outstanding correlated MD event and to drive `tick()`.
`tick()` returns `waiting` while the caller says an event, source IPC request
or inbound datagram is still pending. Once quiescent, it rechecks context,
asks the caller to clear the cache and reset the sampler baseline, checks
quiescence again, and invokes the freeze acknowledgment once. Only then does
it report `frozen`; the caller may issue X4's pause separately. `resume(id)`
may only be called after the caller independently confirms local X4 is
running under the same grant. It resumes the cache, verifies quiescence,
reenables scheduling and invokes the resume acknowledgment once.
The quiescence predicate must exclude the one correlated FREEZE or RESUME
control request currently being serviced; it must still reject any other
pending request, staged sample or queued inbound datagram. Otherwise that
control request would make its own acknowledgment impossible.

The callbacks execute synchronously on the existing owner thread; enabling
scheduling may only change a flag until that owner resumes its update loop.
Request IDs must increase, but may skip IDs consumed by other IPC messages.
The actual source IPC remains responsible for authenticating and correlating
the request, enforcing its own full request sequence and confirming replies.
These callbacks are trusted, stable local adapters; `guard` must check the
owned actor, grant, process and running state without mutating them. Checks
are sampled, not atomic. Timeout, lost context, malformed callback result,
overlap or reentry fences this barrier. On every failed operation, the barrier
sets its state to failed and calls `stop_scheduling` before returning; that
callback must be idempotent and able to disable its local scheduling flag even
after context loss. If disabling cannot be confirmed, it reports
`scheduling_uncertain`, or `ack_and_scheduling_uncertain` if an ACK may also
have been sent. Once the acknowledgment callback is
entered, any exception, failed callback, late result or late inbound packet
reports `ack_uncertain`: delivery may have occurred, so there is no retry.
Returning a callback success is not independent proof of network receipt.

## Required integration work

* `source_motion_sampler.lua` has no idle-only baseline-reset operation today.
  Add one that verifies the same local actor and clears the previous pose/rate
  basis while preserving the local capture counter and last emitted game-time
  fence. Equal game time after resume must be suppressed instead of emitting a
  duplicate timestamp. Do not reset while a correlated read is outstanding.
* `client_authority_motion_reader.lua` currently keeps its actor and sampler
  private. Expose a guarded, local-only identity inspection and idle baseline
  reset; never place the native actor or sector handle on the wire. Preserve
  its existing one-event route and provisional sample staging checks.
* In `client_authority_motion_session.lua`, an opt-in mode may drive the
  reader while registered even without a `PULL`. Commit the staged sample to
  `fixture_player_latest_cache` only after `reader:event()` returns true and
  the grant/actor/sector checks pass again. Pulls consume at most one new
  cached sample. The cache's source/frame token is local correlation only;
  it does not establish the server's coordinate frame or authority.
* `source_motion_ipc.lua` currently knows PULL, registration and optional STOP,
  but no drain/freeze or resume request. A negotiated, versioned extension
  must keep its request IDs, leases and exact ACK matching, accept the pending
  MD event while draining, and refrain from scheduling another read. The
  worker's `GuardedParticipant.pause()` must wait for the freeze ACK before
  sending X4's local pause; on resume it must first confirm X4 running, then
  complete the resume handshake. Missing or ambiguous ACK fences the session.
  The existing post-pause `session:quiescent()` assertion alone cannot safely
  handle continuous sampling: a legitimate MD read can be in flight.
* Existing `SAMPLE2` has one sequence and current Python consumers require it
  contiguous. Sending the cache's delivery sequence in that field is
  syntactically compatible only under an explicit matched opt-in; the
  recipient then cannot inspect the original local capture sequence. A new
  negotiated frame carrying both delivery and capture sequence is required
  to prove their distinct meanings across the wire. The first delivered sample
  after start/resume remains rate-less. Older intermediate captures may be
  skipped; reliable creation/destruction events stay separate.
* Cache age currently starts at successful local cache commit, not at actual
  X4 pose acquisition. A future native adapter should carry a conservative
  local monotonic read-start bound to the cache if it needs to limit time spent
  inside MD as well. Neither bound proves the subsequent network transit age.

Synthetic tests exercise asynchronous waiting, timeout, callback failure,
late event/ACK, reentry and composition with the standalone cache. They do
not establish native event scheduling, local pause acknowledgment, equal
cross-process coordinate frames, Windows/Internet behavior or gameplay.
