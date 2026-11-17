# Private fixture latest-value player source

This is an opt-in diagnostic for the existing two-player fixture, not general
multiplayer. Use `--fixture-player-source-latest-cache` with the existing
`--fixture-player-source-sectors` and fixture-overlap options. Without the
flag, the existing pull-driven source remains in use.

After the saved fixture ship has been registered, the client samples locally
at the existing sampler interval. A pull returns the newest unconsumed sample;
older captures can be overwritten. Capture sequences are local and contiguous.
The existing SAMPLE2 field carries a separate contiguous delivery sequence, so
the UDP format and worker contract do not change. Velocity and angular rate
come from adjacent local sampler readings, never from the pull interval. A
first delivery or delivery after a detected pause has no claimed rate.

The source checks the local controlled actor and sector around cache operations.
The frame token is only a local correlation value: it is not evidence that two
X4 processes share an identical coordinate frame. A successful result does not
prove server application, cross-client visibility, reconnect, native replay,
or gameplay.

The current pause path accepts a pause only when there is no pending descriptor
request, staged sample, or queued protocol packet. It fences the source on an
outstanding request. After resume it clears the cache and sampler derivative
baseline before sampling or delivery continues. This is not the separate
asynchronous freeze/drain protocol; that protocol is not integrated or proven.

Once per client session, a successful local delivery can log
`AUTH_FIXTURE_PLAYER_LATEST SKIPPED <capture> <delivery>` when capture is
greater than delivery and the delivered sample contains velocity. This is
local path evidence that a newer measured sample replaced an older capture;
it does not by itself establish receipt, application, or native correctness.
The synthetic worker chain exercises the wire path with a deliberately slow
pull and verifies the delivery sequence and locally calculated velocity.
