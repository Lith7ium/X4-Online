# Saved-actor one-shot setter diagnostic

This opt-in experiment uses two isolated Linux X4 profiles and disposable
copies of a marked save. Before resuming, each process reads the saved registry
ship and station anchors under its own pause guard. A source sample for saved
index 1318 is delivered over the existing local TCP/UDP path to a client hold
buffer. The client then attempts a single setter operation, with a separately
correlated later MD/FFI readback before `APPLIED`. This is a bounded diagnostic;
it does not certify collision clearance, cross-process frame identity after
resume, continuous motion, or a usable multiplayer session. The sample and
one-shot apply are not a general movement algorithm.

## First attempt

On 2026-11-16, `.local/authority-saved-setter-pair-01/result.json` reported
`success=false`, `error="frame or setter owner fault"`, and
`setter_outcome_uncertain=true`; owned process cleanup was confirmed. Each X4
engine log records the requested checkpoint load, expected marker and observed
pause, then `AUTH_FRAME_READ DONE` with eleven station rows and the saved ship.
The client logged `AUTH_PARTICIPANT_MOTION BUFFERED 1318 1` for
`cluster_115_sector001_macro` at source game time `3.2279604759999998`, then
`AUTH_PARTICIPANT_JOB ERROR apply`. The retained X4 logs contain no
`AUTH_MOTION_APPLY INTENT`, `WRITE_ENTERED` or `READBACK` marker.

In the installed client owner, the exact `ERROR apply` label originates from
the writer's fault callback. The recorded error and installed control flow
therefore indicate that the owner accepted an APPLY matching its last bound
sample, constructed the writer, and invoked its `begin`, `event` or `tick`
path. A rejected mismatched APPLY would instead have produced the outer `tick`
fault. The client log advances from 3.57 to 3.79 game seconds between BUFFERED
and the error, but this is not a measurement of elapsed real time and cannot
confirm or exclude the configured 15-second real-time deadline. The failed
result retains neither sample coordinates nor worker/socket frames, so the
5–50 m displacement condition cannot be reconstructed.

The installed writer's control flow logs INTENT and WRITE_ENTERED before
calling `SetObjectSectorPos`; therefore the retained log and code are
consistent with a failure before that setter call. There is no independent
FFI call trace, however, so the conservative result's uncertain setter outcome
is retained. No TCP receipt for a successful apply or successful readback was
recorded. The old fault message did not identify which guard, MD response,
local FFI inspection, game-time read or target-distance check failed; these
artifacts do not establish the cause. No repeat was run as part of diagnosis.

Following this attempt the diagnostic gained a fixed allowlisted error stage
(`apply_pre_inspect`, `apply_pre_distance`, and other phase codes), with
focused fake-X4 and failure-path tests. Codes describe the failing code stage,
not a recovered cause for this already completed run. Distance, identity,
checkpoint and timing guards remain in force; an error at or after
WRITE_ENTERED continues to mean that a side effect may have occurred.
