# Position snapshots with explicit clock units

The opt-in TCP snapshot schema `version=3` contains exactly `version`, `epoch`,
`generation`, `index`, `sequence`, `sector_macro`, `source_time`, `capture_time`,
`x`, `y`, `z`, and `real_velocity`. `source_time` retains X4 game seconds;
`capture_time` is monotonic source real seconds. XYZ is metres and
`real_velocity` is XYZ metres per real second, or null when unknown. Its range
is ±5000 on each axis. Both times are finite numbers in [0, 1e12]; booleans
are rejected. Capture time does not establish synchronized client/server clocks
or measured network latency.

Within a registered lifetime, capture time must strictly increase and game time
must not decrease. A game-clock stall is allowed. V1/V2 retain strict game-time
progression and their existing rate contracts. Snapshot versions cannot change
within a track, including samples replaced before transmission. Sequence numbers
remain strictly increasing and may skip. Cross-frame rates must be unknown;
recipient frame changes still require resynchronization.

V3 excludes legacy `velocity`, `orientation`, and `angular_rate` fields. The
canonical digest covers both clocks and the real-time rate. Despawn stays V1.
Native one-shot preflight/apply stays V1-only; schema support is not evidence
of native playback or clock synchronization.

## Implementation boundary

The source sampler opts in with `real_time_motion=true`; orientation and this
position-only mode cannot be combined. Its native descriptor adapter requires
an explicit `capture_clock` callback and reads it around the pose query. The
sampler checks capture-before against the preceding reader's capture-after,
including across tracks, and requires per-track capture-after to advance even
after a derivative-baseline reset. `net.monotonic` is a candidate clock: its
native implementation uses CLOCK_MONOTONIC on Linux and performance counters
on Windows. No X4 run of this new capture mode has been performed.

The source IPC marker is SAMPLE3 with 18 fields:
`S|lease|attempt|SAMPLE3|epoch|generation|request|index|sequence|sector_macro|source_time|capture_time|x|y|z|real_vx|real_vy|real_vz`.
Unknown rates encode as `-|-|-`. The Python source bridge and admitted generic
TCP receiver preserve both clocks, validate progression and acknowledge the
complete sample digest. This path has been checked with synthetic source and
participant callbacks over actual loopback UDP/TCP.

Native participant BIND/playback and client-authority motion still reject V3.
No ordinary source-session configuration enables it yet. The next step is a
versioned BIND3 path and playback adapter that uses capture time and real rates
without substituting those values into legacy game-time fields. Existing
continuity, freshness, prediction and correction limits remain unchanged.
