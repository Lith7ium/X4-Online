# Disposable client-to-server one-shot diagnostic

This opt-in runner has not itself established a successful X4 run. It reuses
private profiles, pinned staged saves, owned-process cleanup and the existing
paused frame screen. Both processes must finish the same-run anchor observation
before the client resumes. A synthetic grant admits the client reader and a
synthetic TCP session carries actual client samples of saved index 1318.
Before resuming the server, the worker compares at most 12 samples, over at
most 20 seconds, with the same-run server ship position recorded by the paused
frame screen. It selects the first genuine sample between 5 and 50 units away;
only that unchanged sample reaches the server-local motion owner. If none is
found, it neither resumes the server nor dispatches APPLY. The position is
bound to the frame nonce, local identity and game-time record and checked
against the final X4 log on success.

The server resumes after a candidate is selected. The earlier paused position
is a candidate filter, not evidence of a continuous pause or a write
authorization; its cross-process frame assumptions remain unproven. The
server's local saved-actor binding and
read-only preflight must succeed before a single APPLY is dispatched. NEAR,
FAR, lost context, timeouts and uncertain identity fail closed; there is no
retry, synthetic job acknowledgement or fabricated target. The test may be
inconclusive simply because the live distance lies outside 5–50 units.

`IMMEDIATE` is a local FFI position observation immediately after the write,
with renewed local identity and context guards. It does not establish stability
on later ticks. A separate correlated MD/FFI read after game-time advancement
and at least one real second remains required for a successful receipt and must
still be within three units of the original target. In particular, NPC movement
can make the late condition fail even if a write occurred; no velocity-based
extrapolation is used to call this success. Any failure after possible dispatch
is reported as an uncertain setter outcome.

The opt-in `POST_OBSERVED` marker records the later local position, current
and write-time server game clocks, elapsed real time and distance from the
target before the unchanged success check. It may therefore appear on a failed
attempt; its presence alone is not a successful readback or receipt.

The observed anchors and local checks do not prove equivalent frames in all
conditions, persistent checkpoint identity, collision clearance, gameplay,
internet connectivity, Windows compatibility, or actual HA transfer. Actor
handles stay local. Worker/control receipts, game logs and process/socket guard
checks are distinct evidence; the diagnostic does not capture packets.

## Attempt 01: preflight too near

On 2026-11-16, `.local/authority-client-to-server-apply-pair-01/result.json`
reported `success=false`, `server readback receipt missing`, and a conservative
`setter_outcome_uncertain=true`. It reports no owned processes remaining and
confirmed cleanup.

Both X4 engine logs show a requested load, marker and pause, followed by the
frame screen's `DONE` for 11 station references and the ship. The logged
paused ship position in both processes was `(-131813.265625,
1456.1710205078125, -44963.94140625)`. The client log then records index 1318
at client game time `3.1781741530000001` and a second sample at
`3.3292443109999996`, the latter at `(-131815.28125, 1456.1629638671875,
-44962.2265625)`. The server log records that second sample as buffered and
its own preflight at server game time `3.1374813450000003`: local position
`(-131813.265625, 1456.1710205078125, -44963.94140625)`, target equal to
the logged second sample, distance `2.6464123142468226`, and `NEAR`.

The installed worker and local owner are designed to stop at `NEAR` before
APPLY. Neither engine log contains INTENT, WRITE_ENTERED, IMMEDIATE or
READBACK markers. These records do not constitute an independent setter or
packet trace, so they do not override the result's conservative uncertainty.
The worker's intermediate TCP frames and server resume receipt were not
retained separately. The two processes' game clocks need not agree, and the
same-run anchor observations do not prove general cross-process frame identity
or collision clearance. The TCP admission and client grant remain synthetic;
there is no established X4 write, HA handover or gameplay result.

## Attempt 02: immediate match, later check failed

On 2026-11-16, the filtered run in
`.local/authority-client-to-server-apply-pair-02` returned `success=false`,
`participant owner fault` and `setter_outcome_uncertain=true`. The client
logged three actual samples of saved NPC 1318. The server buffered sample 3,
and its local preflight reported `READY` at distance `39.710829953609583`.
The correlated INTENT and WRITE_ENTERED markers were followed by IMMEDIATE
at `(-131843.625, 1456.0355224609375, -44938.34375)`, matching sample 3's
target. This is a point-in-time observation from the server process after the
setter call, not evidence that the position remains controlled.

The server subsequently logged `apply_post_readback`; no READBACK or APPLIED
receipt is present. That failure combines checks for advancing game time, at
least one elapsed real second, and distance within three units. Neither the
individual failed condition nor the later position was logged, so NPC motion
is a possible explanation, not an established cause. No independent setter
trace or general cross-process coordinate proof exists. The server and client
private save copies and archived input retained SHA-256
`64a233ac6a85194b8276212709e78a6c48bbcc0f73c19842622aa098f1408cb8`;
the result reports confirmed owned-process cleanup and no remaining owned
processes. The grant and network session remain synthetic, and this does not
demonstrate persistent control, HA transfer or gameplay.

## Attempt 03: later position measured

On 2026-11-16, `.local/authority-client-to-server-apply-pair-03/result.json`
reported `success=false`, `participant owner fault`, uncertain setter outcome,
and confirmed owned-process cleanup. The client logged three samples of NPC
1318; the server buffered sample 3 and classified its preflight as READY at
28.337202130692745 units. After INTENT and WRITE_ENTERED, IMMEDIATE reported
the sample target `(-131834.890625, 1456.0775146484375, -44945.62890625)`.

The new correlated POST_OBSERVED diagnostic recorded server position
`(-131985.8125, 1455.119873046875, -44825.81640625)`, at server game time
4.1807694600000005 versus 3.1685127799999999 at write, after 1.0122566799999984
real seconds. Its distance from the original target was 192.70019353182462;
the three-unit condition therefore failed, and the server logged
`apply_post_readback`, with no successful READBACK or APPLIED receipt. These
local observations establish a changed position between the two reads, not
which engine subsystem moved it, a shared frame in general, or continuous
client control. Both private save copies and the archive retained SHA-256
`64a233ac6a85194b8276212709e78a6c48bbcc0f73c19842622aa098f1408cb8`;
no X4 process was visible on the independent post-run check. The trial used
synthetic admission and does not establish HA handover or gameplay.
