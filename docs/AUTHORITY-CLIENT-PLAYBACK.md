# Buffered client playback (internal, opt-in)

`motion_playback.lua` connects the existing motion buffer to repeated XYZ
corrections. `motion_client_owner.lua` can drive it from its existing update
loop after the saved-registry binding resolves. No additional update hook,
socket reader or server coordinator is created. This is an implementation
increment, not a native movement or playable-multiplayer result.

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

The installer and independent native CLI do not yet expose this playback
configuration. They must install the module, enable it under the current owner
hook and collect bounded evidence before a native test can be run.
The existing native binder also requires a running game. Generic controller
pause tests therefore do not establish that a native bind can span a pause;
the runtime must stop/drain binding before pausing or implement explicit
suspension. Its existing running-state guard has not been relaxed.

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
focused tests; it is not yet wired into the native CLI.

The next native experiment must deliver moving samples through the existing
local motion IPC, measure actual positions, and acknowledge STOP before the
server-driven pause. It must distinguish correction/readback success from
AI suppression, visual smoothness and shared-world synchronization. Player
controls, remote orientation, cross-sector transitions, Windows and Internet
gameplay remain outstanding.
