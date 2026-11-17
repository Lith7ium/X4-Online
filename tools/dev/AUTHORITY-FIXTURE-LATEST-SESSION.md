# Private fixture latest-value player source

On 2026-11-17, an isolated Linux loopback run recovered a previously confirmed
fixture checkpoint, admitted two X4 clients in distinct sectors, collected
their stationary player tracks, and then disconnected and rejoined one client
while the other remained. The normal join lifecycle paused and resumed the
remaining participant through the opt-in freeze/drain path. Its first delivered
sample after resume had no velocity or angular rate; both participants then
provided further complete samples. The last departure produced confirmed
checkpoint `checkpoint-9f85eb2743d543a5afa4321d7d16110b` (SHA-256
`e236c26d9dd77003524e6d6ed0fff8bf5ce24ab469b9c5dfeb6799e790efc2c4`).
The outer process/display cleanup succeeded and Steam identity was unchanged.
Results are under `.local/private-fixture-player-rejoin-scope-real-20261117-01/`.
This result does not prove moving ships, server-side motion application,
combat, trade, Windows, Internet connectivity or playable multiplayer.

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

With the default pause path, a pause is accepted only when there is no pending
descriptor request, staged sample, or queued protocol packet. An outstanding
request fences the source. After resume it clears the cache and derivative
baseline before sampling or delivery continues.

A separate experiment, `--fixture-player-source-freeze-drain`, requires the
latest-cache option and explicitly enables the same protocol at both ends.
Once the worker has bound a source, it requests a correlated freeze before
asking X4 to pause. The source stops scheduling reads, drains an outstanding
descriptor callback, clears the cache and derivative baseline, and replies
`FROZEN`. The worker requests `RESUME` only after the X4 resume is confirmed;
the source replies `RESUMED` before sampling resumes. The receiver requires the
first delivered sample after resume to have no velocity or angular rate, even
if intervening pulls return no sample. An unexpected X4 pause, mismatched
reply, deadline expiry, or uncertain transport result fences the source; a
lost acknowledgement cannot safely be retried. If the source has never been
bound, there is no active sampler to drain.

The freeze/drain path has synthetic tests with the Lua source, IPC, and worker,
including a delayed descriptor callback; it has not yet been tested in X4.
The acknowledgement and process guards provide bounded checks, not an atomic
proof against every possible packet or process change after the final check.

Once per client session, a successful local delivery can log
`AUTH_FIXTURE_PLAYER_LATEST SKIPPED <capture> <delivery>` when capture is
greater than delivery and the delivered sample contains velocity. This is
local path evidence that a newer measured sample replaced an older capture;
it does not by itself establish receipt, application, or native correctness.
The synthetic worker chain exercises the wire path with a deliberately slow
pull and verifies the delivery sequence and locally calculated velocity.


For a bounded native rejoin candidate, add
`--fixture-player-source-rejoin` alongside the fixture-overlap, sector,
latest-cache and freeze-drain options. The runner first obtains both players'
source samples, suspends authority delivery, disconnects slot 1 and keeps slot
2, then rejoins slot 1 with a fresh grant. The ordinary join pauses and resumes
the surviving participant; after the new participant is admitted, both
sources are read again. The surviving source must supply a fresh rate-less
baseline. With quick guards enabled, the runner opens a separate verified pin set for
each sampling phase. It closes the first set and restores full file hashes
before departure, saving, and rejoin; only after the replacement is admitted
and fully checked does it pin the actual survivor and replacement save paths.
The existing exclusive-writer and file-descriptor ownership assumptions remain.
Without quick guards, full file hashes apply throughout.

A real-TCP test with simulated clients exercises the coordinator and owner
transitions, including rejection of stale post-resume velocity. This is not an
X4, Windows, or Internet test; no native rejoin or gameplay is established.
