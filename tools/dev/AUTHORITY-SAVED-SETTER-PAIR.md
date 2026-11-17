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

The local writer additionally supports an explicitly selected, fixed
`recovery_enh_870` fixture: registry epoch
`4ba7be438ebb04ec5bb85fdb95b5a488`, index 1318,
`cluster_06_sector001_macro`, code `ENH-870`, macro
`ship_arg_m_trans_container_02_b_macro`, owner `antigone`. Without that
selection the original `WRG-830` fixture remains the default. The optional
router must also be configured for this exact fixture; its epoch and index
checks and matching pre/post Inspect arguments remain in force. The writer and
MD inspect repeat local identity and existing safety checks. The epoch alone
does not prove checkpoint provenance or cross-process identity.

Offline tests compose the actual recovery client wrapper, saved binder, motion
owner, event router and writer with simulated MD responses and a fake X4 ABI.
They do not execute the MD file in X4. The recovery installer and active probe
now connect this option only when explicitly requested. No recovery-specific
two-process frame fence or native setter effect has been established. This
fixture is not gameplay evidence.

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

## Second attempt

On 2026-11-16, `.local/authority-saved-setter-pair-02/result.json` again
reported `success=false`, `error="frame or setter owner fault"` and
`setter_outcome_uncertain=true`, with owned cleanup confirmed. The X4 engine
logs show both paused frame reads completing and the client logging
`BUFFERED 1318 1` before `AUTH_PARTICIPANT_JOB ERROR apply_pre_distance`.
No INTENT, WRITE_ENTERED or READBACK marker appears in the retained logs.

The installed writer assigns `pre_distance` after a correlated positive MD
response, local FFI inspection, guard and game-time checks. That stage computes
the Euclidean distance between the locally inspected client position and the
received source position and requires it to be finite and within 5–50 m
inclusive. Thus the code and log identify a non-finite value, a distance below
5 m, or a distance above 50 m; the artifacts do not record those positions or
the distance, so they do not distinguish these cases. The installed control
flow puts the distance check and both markers before `SetObjectSectorPos`;
there is no independent FFI call trace, so the saved result's conservative
uncertainty remains. The test does not prove a successful write or readback.

## Candidate read-only preflight

A minimal next experiment would add a separate, explicitly opt-in read-only
preflight request after BOUND and before any APPLY. The client would repeat the
correlated saved-actor MD/FFI checks, compare its current local position with
the exact last bound, fresh source sample, and return/log their identity,
positions and calculated distance. This check would neither call the setter nor
consume the one-shot APPLY. The caller could obtain and bind a new genuine
source sample within a bounded observation period when the distance is below
5 m, then repeat the preflight. An invalid/non-finite or greater-than-50-m
result, lost identity/guard, expiry or timeout would fail closed. The window
may finish without a suitable sample; no position would be invented to force
success. Only after a suitable preflight could the caller submit APPLY for
that same still-fresh bound sample; the existing setter must independently
repeat its checks because the actor can move between preflight and APPLY.
After any possible write, do not retry automatically. This design still would
not establish collision clearance or cross-process frame equality.

## Implemented local preflight

The experimental client owner now accepts an explicitly enabled, correlated
`PREFLIGHT` only for the most recently BOUND saved sample. It issues its own
MD inspection and reads the matching local actor and sector through the same
FFI and running/checkpoint/age guards used by the one-shot writer. The local
`PREFLIGHT` marker records request, index, sequence, sample digest, both
positions, client game time, calculated distance and `NEAR`, `READY` or `FAR`.
Only finite distances strictly below 5 m yield NEAR; finite values from 5 m to
50 m inclusive yield READY. FAR is logged then faults the session; invalid or
non-finite values fault without granting permission. The preflight does not
call the setter or consume APPLY. A fresh BIND invalidates previous READY;
replayed request IDs or a second preflight for one BIND fault. The isolated
owner retains at most 100,000 operation IDs, then fails closed. APPLY requires READY for the same still-bound,
fresh identity and digest and independently repeats the live checks. The
position can change between the two inspections. Errors after WRITE_ENTERED
remain uncertain, and the preflight is not a collision-clearance or common
frame proof. Fake-X4/MD tests cover this code, not a native X4 execution.

## Third attempt

On 2026-11-16, `.local/authority-saved-setter-pair-03/result.json` reported
`success=false`, `frame or setter owner fault`, and confirmed owned cleanup.
Both X4 logs contain `AUTH_FRAME_READ DONE`; the client logged a buffered
sample for index 1318 followed by a correlated PREFLIGHT record. Its local
position was `(-131891.40625, 1455.763671875, -44899.66015625)` and its
received source position was `(-131815.671875, 1456.161376953125,
-44961.8828125)`. The logged distance was `98.017920181849689` m, so the
preflight reported `FAR` and the client logged `preflight_pre_distance`.
These are readings at different process times; they do not establish a common
running frame. No INTENT, WRITE_ENTERED or READBACK marker was recorded. The
installed code does not authorize APPLY for FAR and no setter is expected;
there is no independent setter-call trace, and the failure result retains
`setter_outcome_uncertain=true`. The result does not prove a write, receipt,
frame identity, collision clearance or gameplay.

## Private recovery join one-shot

The recovered loopback supervisor has a default-off `--diagnostic-saved-apply`
option. It requires `--registry-witness-join`, `--diagnostic-client`,
`--diagnostic-source-index 1318`, `--diagnostic-client-motion`,
`--diagnostic-local-pair`, and `--diagnostic-local-pair-delivery`, as well as
the pinned registry epoch above. Existing recovery, process, membership,
checkpoint, deadline and STOP guards remain in force. This is one client and
one selected saved actor in disposable local Linux profiles.

After the exact pair sample and its client receipt are confirmed, the probe
performs at most one preflight. NEAR causes no write; FAR, invalid results or
errors abort. READY allows one APPLY only after `saved-apply-intent.json` is
created exclusively and its file and directory are fsynced. That marker means
that an effect may follow; it does not mean a write actually happened. A lost
or ambiguous response is never retried automatically. The marker survives a
normal process interruption, but power-loss durability of all newly created
ancestor directories has not been established. The recorded host receipt to
apply time is a lower bound; the sample's complete age is unknown.

`test_authority_recovered_apply_worker_chain.py` exercises the source probe,
TCP, worker, recovered client wrapper and actual Lua writer using simulated MD
and a fake X4 ABI. In that test the fake client checks the intent digest before
its one simulated write and explicitly reports one write after STOP. It is not a
native X4 run. No common running frame, collision clearance, continuous motion
or gameplay is established by this option. In particular, a local preflight
cannot prove that the independently running worlds have equivalent frames.
