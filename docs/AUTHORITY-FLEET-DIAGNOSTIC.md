# Local 12-fixture fleet diagnostic

This is a **read-only loopback experiment**, not the multiplayer protocol or a game-state synchronizer. It does not choose simulation authority, find ships, establish persistent identities, convert X4 frames, apply positions, save the game, or connect over the Internet. The twelve identifiers and their coordinate frames must be established independently for both processes before a native experiment. An identical string is not evidence that two X4 objects represent the same ship.

## API for an isolated experiment

* Start `authority.fixture_fleet_udp.FixtureFleetUDP` with `fixtures` as exactly twelve `{fixture: frame}` pairs, a source lease, one to eight guest leases keyed `GUEST1` through `GUEST8`, and a finite maximum source age in seconds. Every lease must be a distinct random 128-bit value represented as 32 lowercase hexadecimal digits. Supply the port, registry and each participant's own lease privately; do not put leases into public files, command lines or logs. The adapter accepts only IPv4 loopback and pins each role to its first registered socket endpoint. Call `poll()` frequently; it consumes at most 64 datagrams per call. The caller owns socket lifecycle and must call `close()`.
* On a participant, load `fixture_fleet_wire.lua` and supply the existing nonblocking `x4lan_net` connection: `wire.new(connection, role, lease, fixtures, max_reply_age)`. The last argument is mandatory for guests, in seconds, and bounds how long a guest accepts an answer after its own request was sent. A source calls `wire:step(samples)`, where `samples` maps any subset of known fixture IDs to `{x, y, z}` finite coordinates. A guest calls `wire:step(nil, now)`, where `now` is a nonnegative monotonic clock in seconds supplied by the host. It returns only newly accepted updates, each with `fixture`, `frame`, `request`, `source_sequence`, `x`, `y`, and `z`. Do not reuse the latest returned update indefinitely: there is no client-side retained-state expiry mechanism.
* Register all twelve identities and frames before constructing either side. Frames are opaque fixed strings, not a frame conversion or a proven X4 sector ID. Samples not supplied on a source step are not resent; server-side expiry prevents indefinite use. The guest rejects replies for unknown frames/fixtures, requests it did not make, expired replies, duplicates and older source or request sequences. It retains at most 64 outstanding requests per fixture. The guest clock must remain monotonic throughout the lifetime of the instance. A fresh adapter and fresh leases are required for a restarted session.
* Both roles retry registration until `READY`. Each source step emits at most twelve samples. Each ready guest step emits twelve independent requests, whether or not a sample exists, and drains at most 64 replies. A slow poller, packet loss or full OS buffers can drop updates; no delivery, ordering, pacing, fairness, reconnection or congestion-control guarantees exist.

The server checks freshness against the time a sample reaches its socket; it cannot prove when X4 captured that sample. The guest bounds the age of its request, but cannot independently prove the real capture time of the sample in the response. Its local clock is injected and not network-synchronized. A later native harness must protect the experiment's processes, snapshot and test profiles independently.

## Datagram format

All packets are ASCII with `|` field separators and at most 512 bytes. IDs and frames contain 1–64 ASCII letters, digits, `_`, `-` or `.`. Decimal sequence numbers range from 1 through 2^53−1 and are strictly increasing per fixture per role; coordinates must be finite decimal values.

```
participant -> adapter: FLEET1|HELLO|SOURCE or GUESTn|lease
adapter -> participant: FLEET1|READY|SOURCE or GUESTn
source -> adapter:      FLEET1|PUT|source-lease|fixture|frame|source-sequence|x|y|z
guest -> adapter:       FLEET1|GET|guest-lease|fixture|frame|request-sequence
adapter -> guest:       FLEET1|POS|fixture|frame|request-sequence|source-sequence|x|y|z
```

An absent, expired, invalid or stale sample receives no position response. An accepted GET advances its guest/fixture request sequence even if no fresh sample is available. Registration retries for the same endpoint resend READY. No role may change endpoint or share another role's socket in an adapter lifetime. Leases protect this local diagnostic from accidental cross-talk only and are not Internet authentication.

The tests in `tests/test_authority_fixture_fleet.py` exercise a Python adapter over real loopback UDP sockets, and compile the existing native socket module for a LuaJIT source and two LuaJIT guests. They are synthetic tests outside X4; they do not establish Windows operation or gameplay.

## Optional native harness

`--authority-fixture-fleet` requires `--authority-fixture-scan`,
`--authority-fixture-wire`, two local processes and at least 300 ticks. Both
processes must resolve each of the twelve enrolled handles to the corresponding
snapshot fixture identity and a saved sector; all twelve must be in one pinned
sector, whose private digest must match between processes. The source samples
all twelve independently. The guest does not apply positions. The experimental
test uses Linux `CLOCK_MONOTONIC`; if the clock, saved sector identity, or
another prerequisite is unavailable, it fails rather than asserting freshness.
Leases travel through a private pipe and per-process mode-0600 configurations;
new authority bundle and run directories are created mode 0700.

The validator checks each fixture separately: every received coordinate must
match a source sequence for that fixture, every observed capture age must be
between zero and two seconds, and after tick 90 at least three samples with no
gap longer than 120 ticks must cover the remainder of the run. These are
bounded diagnostic acceptance thresholds, not a gameplay performance target.
The independent fleet scan and the rest of the runner remain mandatory. If
`--authority-fixture-motion` is also enabled, the separate single-fixture wire
check requires the transmitted first fixture to move at least 10 m. This
native harness is implemented and synthetic-tested, but not yet executed in X4.
