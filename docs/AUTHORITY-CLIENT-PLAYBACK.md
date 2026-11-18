# Buffered client playback (internal, opt-in)

`motion_playback.lua` connects the existing motion buffer to repeated XYZ
corrections. `motion_client_owner.lua` can drive it from its existing update
loop after the saved-registry binding resolves. No additional update hook,
socket reader or server coordinator is created. One bounded native playback/STOP/
pause trial passed with a private Wait-plus-zero-velocity intervention. Default
NPC playback still faults; see the
[integration report](../reports/AUTHORITY-CLIENT-PLAYBACK-20261117.md).

## Data and lifetime

The controller receives source-time positions and optional linear rates,
with the original local receive time. It interpolates and performs bounded
prediction through `motion_buffer.lua`; source and receiver absolute clocks
need not agree. Source sequence/time and local arrival ordering remain checked.
A binding may finish after intervening rendered frames. The explicit
`deferred_arrival` buffer mode permits that original timestamp without
relabeling binding completion as reception or suspending previous playback.
Other buffer users retain the stricter default behavior.

Every active frame reads actual engine position, including when the requested
position is unchanged. The following tick observes the previous write before
another correction. This is a point-in-time readback, not proof that game time
advanced or the engine settled at that target. Local arrival age eventually
stops corrections even when the buffer has a frozen prediction. A fresh newer
sample may resume an expired track. Pauses invalidate samples; packets received
during the pause cannot revive playback after resumption.

The saved actor, sector and zone remain fixed for each track. A changed binding,
failed guard, invalid clock or uncertain native write ends that playback. STOP
disables writers before bindings and transport close. The owner retains an
uncertainty flag if the last write has not been observed. Late events cannot
restart a stopped track.

In playback mode, `BOUND` confirms a correlated binding and consumption of the
packet. A paused or expired sample may be consumed without insertion into the
playback buffer. Neither `BOUND` nor a successful setter call proves native
movement. Readback evidence is separate.

## Native adapter and current limits

`saved_motion_apply.new_playback_x4` reuses the existing private-profile,
fixture identity, operational state, dock state, player exclusion, sector and
zone checks. It retains the independent fixture index/epoch/sector checks
previously enforced by the one-shot entry point. The original one-shot apply
state machine remains separate and unchanged.

Only XYZ playback is enabled. The adapter preserves the actual local rotation;
it does not adopt remote orientation or set native constant velocity. Velocity
is used for prediction. It supports the two existing isolated fixtures and
limits each correction to a configured maximum of 50 metres. The general
controller accepts a larger configured limit; the fixture bound is not a
universe-wide movement policy. This code does not suppress native AI or physics.
The historical angle conversion still needs confirmation in a real playback run.

The optional `motion_client_owner.new_x4` configuration includes:

```lua
saved_playback = {
    enabled = true,
    module = X4LAN_SAVED_MOTION_APPLY,
    playback = X4LAN_MOTION_PLAYBACK,
    fixture = 'recovery_enh_870',
    max_step = 50,
    record = record_playback_summary,
}
```

This fragment supplements the existing saved-baseline owner configuration;
it is not a standalone launcher. `saved_apply` and `saved_playback` are mutually
exclusive. The recording callback must return true and should aggregate or
rate-limit output; it receives observations/readbacks with portable track
identity, never native actor handles.

The recovered-client installer now accepts the explicit setting
`saved_playback_fixture='recovery_enh_870'`. It installs the playback module
under the existing update owner and restricts this diagnostic to saved registry
index 1318 in the retained ENH-870 checkpoint. The first BIND resolves identity
and records INITIAL from the native position; its arbitrary target is discarded.
Only subsequent increasing XYZ samples enter playback. The runtime emits one
INITIAL, up to 64 summaries at no more than one per second, and one STOPPED
record. A distance fault adds at most one captured FAILURE observation without
another native read. No native handles or connection credentials appear in these
records.

The independent Linux CLI exposes `--internal-saved-playback-config FILE` only
with a Python `playback_driver` callback or `LiveSourceInput` passed to `run` or `main`. This remains
a private test interface, not a player-facing network motion service. The strict
configuration pins the offered checkpoint, registry, complete content file and
four archived saved MD scripts. Installation and ordered marked-registry checks
precede admission. A worker owns the local motion UDP bridge; the main thread
continues owning admission, native participant controls and lifecycle polling.
The worker starts only after a confirmed server resume.

After source silence, the controller reads back its last correction and reaches
its hard one-second age limit. STOPPED must report drained state and no uncertain
write before the private harness can request a server pause. Native process
cleanup precedes worker release, join and configuration redaction. The default
load/control client path remains unchanged.
The existing native binder also requires a running game. Generic controller
pause tests therefore do not establish that a native bind can span a pause;
the runtime must stop/drain binding before pausing or implement explicit
suspension. Its existing running-state guard has not been relaxed.

## Bounded live source input

`tools/dev/authority_native_client_stream.py` adds an in-process input for this
same one-ship diagnostic. Inject an exact `LiveSourceInput` instance with the
pinned epoch, index and sector as `playback_driver`. The independent client then
attaches its `accept_motion` callback to the existing admitted TCP owner. It
does not create another TCP reader. The callable synthetic driver remains
available for its original diagnostic.

The producer must wait for `wait_ready(timeout)`, which observes the playback
worker's client INITIAL boundary. It can then send through the existing motion
protocol, or call `submit(sample, received_at=time.monotonic())` directly in an
isolated harness. `finish()` explicitly ends this finite input; `fail()` records
a producer failure. There is no new network readiness or end-of-stream message.
The future source supervisor must coordinate those boundaries before native use.
Packets before readiness or after EOF are rejected.

Source XYZ, game time and nullable velocity remain unchanged. Unknown velocity
is not replaced with zero. Source sequence and generation are retained in the
diagnostic provenance; local UDP enrollment uses sequence 1, so subsequent
deliveries receive explicitly recorded local sequence numbers and the existing
local generation. Generation identifiers are hashed in evidence. The first
source pose must be within 50 metres of client INITIAL; no coordinate translation
or clock rewrite is performed to meet that limit.

The queue defaults to two pending samples, at most 64 samples and ten real
seconds. It rejects overflow, stale or future producer receipts, identity
changes and regressing sequences/timestamps. These are finite diagnostic limits,
not the production policy for slow network clients. Receipt age is checked
before local UDP dispatch. The Lua buffer still timestamps its own UDP arrival;
the Python receipt time is retained as evidence, not substituted for that arrival.
Observed source-game/receipt-time ratios do not prove equal simulation speeds.

A TCP receipt confirms queue acceptance only. Native readbacks and drained STOP
remain separate requirements. This input does not install the private NPC Wait
and velocity intervention. The independent CLI retains its pinned original
checkpoint restriction. The paired supervisor below instead connects the fresh
join checkpoint through its existing verified admission path. Neither wiring
increment establishes a native source-to-client flight.

## Paired supervisor diagnostic

The existing two-process supervisor also has an explicit
`--diagnostic-saved-playback` mode. It requires `--registry-witness-join`,
`--diagnostic-client`, `--diagnostic-source-index 1318` and
`--diagnostic-client-motion`, with the pinned recovery registry and script
lineage. Pair delivery and one-shot apply are forbidden. Fresh checkpoint
admission remains mandatory. This is an internal experiment, not a playable mode.

Unlike the independent worker above, the paired path's existing TCP owner sends
the first actual source packet as enrollment and preserves source sequences
through its single UDP bridge. It waits for client INITIAL after that receipt,
then gathers 25 further packets, drains and stops both ends, and correlates
native readbacks with the source. Its bounded metadata phase has full save
digest checks at the boundaries and retains other live guards. The ordinary
save-check path remains unchanged outside this explicit mode.

This wiring has real local TCP/UDP tests with simulated engine edges only.
The switch does not install the private native08 NPC Wait/velocity override or
release observer. A native paired runner still needs those pinned artifacts and
must pass departure saving as well as movement/STOP/release observation. See
[the current paired integration report](../reports/AUTHORITY-CLIENT-PLAYBACK-20261117.md).

## Validation and next native boundary

The initial focused batch passed 31 tests in 2.617 seconds using the real Lua
buffer/controller/owner with simulated binding and engine callbacks, plus a
compiled fake native ABI. Existing buffer, one-shot apply, saved/replica binding,
owner IPC, STOP and saved-stream checks were included. No X4, Windows, WAN or
full-suite run was performed for this increment. The earlier full-suite failure
and missing prerequisites remain open.

After review, the three new playback tests passed again in 0.055 seconds with
additional paused/expired acknowledgement, guard-loss, callback-stop and
portable record-attribution cases. The unchanged broader batch was not repeated.
Logs are retained in `../x4-client-playback-20261117/.local/` as
`client-playback-focused-20261117.log` and `client-playback-new-final-20261117.log`.
The focused batch was:

```sh
PYTHONPATH=tests:src:tools/dev .local/validation-venv/bin/python -m unittest \
  test_authority_motion_playback test_authority_motion \
  test_authority_saved_motion_apply test_authority_saved_baseline_motion_binding \
  test_authority_replica_motion_binding test_authority_motion_client_ipc \
  test_authority_participant_motion_stop test_authority_saved_motion_stream -v
```

The independent client's previous native load/control test used a checkpoint
with an uninitialized registry. Playback instead needs the existing registered
ENH-870 witness checkpoint and its four compatible saved MD scripts. Local
preparation is retained in `.local/authority-client-playback-native-next.txt`;
its cached metadata requires fresh provenance verification before launch.

`authority_recovered_client_registry.install` and `verify_log` now support
explicit `load_gate='marker'` for the independent client's real marked-load
probe. The default identity gate is unchanged. Marker mode rejects mixed
identity probes/receipts and requires unique ordered load, inspected-marker,
correlated paused registry and pause receipts. This helper has 13 passing
focused tests; the optional native playback path uses this gate.

The native experiment must acknowledge drained STOP before the server-driven
pause. Default playback and a private finite Wait alone failed when X4's actual
position jumped more than 700 metres from the unchanged final target. A private
Wait-plus-zero-linear-velocity contrast passed the complete bounded flow with an
exact 20-metre endpoint and drained STOP. A subsequent private probe established
the captured Wait's current/started state and advancing game time/UI updates
before the velocity request. It again reached the endpoint and drained STOP,
but failed in its new observation bridge after requesting release. Correcting
that bridge's object-reference conversion allowed the next bounded trial to
complete playback, release observation and native pause. Seven read-only samples
over 6.65 game seconds found the temporary Wait absent, the exact prior order
current and started, and about 647 metres of native movement. This establishes
the combined sequence for one saved NPC, not exact AI-stack restoration or a
general NPC control policy; see the report for separate run outcomes.
The intervention is not installed by the production path, and the 50-metre
correction bound remains unchanged. Distinguish this one-ship result from
AI suppression, visual smoothness and shared-world synchronization. Player
controls, remote orientation, cross-sector transitions, Windows and Internet
gameplay remain outstanding.
