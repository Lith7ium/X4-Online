# Experimental latest-motion control poll

`ExperimentalTCPControl.enable_latest_motion(enabled=True, ...)` opts the
existing, single-threaded control owner into `ExperimentalTCPMotion.enqueue_latest`.
The caller must already have registered the track and select only recipients
whose interest and identity are valid. Enqueueing is local acceptance, not a
network receipt, an X4 application, a visibility decision, or proof of gameplay.
The existing participant client and receipt wire format remain in use.

Each admitted socket has at most one started request awaiting its matching
receipt and a bounded, insertion-ordered map of unsent samples keyed by track.
A newer sample for the same track replaces the pending one. The owner finishes
any partially sent frame and waits for its receipt before sending another frame
on that socket. Other sockets continue to be pumped. Slow, disconnected or
invalid peers are dropped individually when their request times out or their
receipt is invalid. A completed receipt asserts only that the participant's
configured callback accepted the sample. The owner remains responsible for
choosing its timeout and fencing any unconfirmed game effects.

`ExperimentalLocalHost.tick` automatically fences new motion and discards
unstarted samples while a pause/save/resume world operation is pending. A
started request must complete or its peer must be dropped before the world
operation begins. For an event, despawn or another synchronous socket owner,
the caller must call `control.motion_barrier()` first, pump `host.tick()` until
it returns true, then run the synchronous operation and finally call
`control.release_motion_barrier()`. Establish this barrier **before** invoking
`gate.begin()` or queueing/flush of a lifecycle delivery: a failed flush after
sending an event to its delivery gate fences the host and cannot be retried.
The normal reader lease is unavailable while motion is pending or in flight;
no second reader is started. Changing a recipient's sector frame still requires
an external resynchronization; that mechanism is not provided here.

The current source bridge continues to use its original synchronous `send`
path; it does not yet pump this queue or continuously stream X4 motion. The
feature has no integrated interest discovery, authority transfer, remote
security, Internet or Windows validation. `tests/test_authority_latest_motion_poll.py`
exercises local TCP with synthetic controllers, not real X4 gameplay.
