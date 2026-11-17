# Fixture player latest-value cache

`lua/fixture_player_latest_cache.lua` is a default-off building block. It
registers no update or MD event handler, performs no X4 call and sends no
network message itself. An explicitly enabled private fixture session now
connects it to the local sampler and adapts its delivery sequence to the
existing sample protocol; ordinary sessions remain unchanged. The building
block also has tests using simulated samplers, clocks and player contexts.

One owner is bound to an explicit grant for player index 3 or 4 and to one
locally controlled actor. The caller must separately establish the actual
grant, local actor, sector/frame, process and source sampler. `authority`,
`inspect` and `validate_capture` are caller assertions, not independent proof.
Clock, guard, authority and inspect callbacks must be trusted, stable
observers; subsequent callbacks must not alter a context that was already
checked. These sampled checks cannot make mutable game state atomic.
Only call `capture` after the owned sampler's correlated event has completely
returned successfully. `validate_capture` must attest the exact supplied
sample is from that sampler, including that every non-null rate came from its
immediately preceding valid local observation in the same lifetime/frame.
The cache does not compute or manufacture velocity or angular rate.

Successful captures have a strictly contiguous local capture sequence and
monotonic source game time. A single latest value replaces older captures.
`pull` consumes it at most once, assigns the next contiguous delivery sequence,
and returns both the original `capture_sequence` and a sample carrying that
new delivery sequence. Capture gaps between deliveries are expected. The
sample's first delivered rate is omitted; later rates are preserved from the
sampler. A local monotonic age bounds cache residence through the last guard
check. It is not a measurement or guarantee of subsequent transport latency.
The fixture adapter unwraps this local envelope and sends the contiguous
delivery sequence through the existing sample protocol; the local capture
sequence is not transmitted as a protocol field.

The caller must stop scheduling new sampler work and drain pending MD events
and IPC before invoking `pause`. `quiescent` must attest that condition and
`reset_sampler` must actually clear the sampler's prior derivative baseline,
while preserving its local sequence counter. The cache then discards pending
values and remains paused until the caller reports that X4 has resumed under
the same grant. The next capture and first delivery require a rate-less
baseline. A spontaneous pause, changed actor/grant/frame, invalid sample,
reentry or failed callback fences the owner. A handover or new lifetime needs
a fresh owner and a fresh grant. All checks are sampled and non-atomic.

This contract neither proves visual smoothness, cross-process frame equality,
native velocity, network delivery nor a playable multiplayer session.
