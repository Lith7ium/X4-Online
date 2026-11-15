# Experimental local X4 control

This is a disabled-by-default prototype for an **isolated test profile**, without client admission or save transfer. It does not call `QuitGame`, `LoadGame` or change the user's normal saves. A separate opt-in [local control bridge](../src/authority/LOCAL_CONTROL_BRIDGE.md) connects it to `WorldCoordinator` and completed an isolated Linux X4 lifecycle with simulated client load confirmations. Neither implementation has been validated on Windows or as a multiplayer lifecycle.

The approach reuses the earlier LAN experiment's `IsGamePaused`, `Pause`, `IsSavingPossible(false)`, `SaveGame` and `gameSaved` mechanisms. It also uses `Unpause` and observed game time. Unlike the earlier one-time pristine-world capture, it never exits X4 and never declares a save complete from an event alone.

## Explicit integration contract

`control_state.lua` exposes the inert factory as `X4LAN_AUTHORITY_CONTROL_STATE` for X4 UI loading; it contains a pure state machine. `new({enabled=false}, ...)`, an absent config, or any value other than boolean `true` returns disabled without touching the engine. An enabled configuration supplies `owner`, `world_epoch`, `timeout_seconds` (default 30), and `pause_settle_seconds` (default 0.1). Owner and epoch are local fencing labels, **not authentication**. The caller must exclusively own this specific X4 process and serialize every call. Creating another state machine for the same process would defeat the one-save fence; it must be forbidden by the future supervisor.
By default the state machine retains the one-save-per-process restriction. An
explicit `enable_verified_reuse=true` opts into a repeated-save lifecycle. One
isolated Linux X4 experiment completed three independently verified saves in
the same slot; see `AUTHORITY-REPEATED-CHECKPOINT.md`. Repeated joins and last
departures still need an integrated multi-save lifecycle and real admission.

`x4_control_engine.lua` exposes the separate explicit factory as `X4LAN_AUTHORITY_X4_CONTROL_ENGINE`. `new({enabled=true, test_profile='45841'})` resolves the required X4 UI functions and confirms that X4 reports a save directory ending in `/45841/save` (either slash convention). The caller must additionally establish that this profile and its game process are disposable and exclusively owned. Nothing in a profile suffix proves process ownership. The binding does not start, stop, load or save the game at construction. `register_save_event(config, state, RegisterEvent)` must be called explicitly once; it registers `gameSaved` and treats a registration error as indeterminate rather than allowing a duplicate retry. Integrate `state:on_update()` into an existing X4 UI update callback: do not install a second competing `SetScript` handler.

The external owner submits exactly one request at a time with:

```lua
state:submit(owner, world_epoch, request_id, 'pause')
state:submit(owner, world_epoch, request_id, 'save', {
  slot='save_009', exclusive_owner=true, empty_owned_slot=true,
})
state:submit(owner, world_epoch, request_id, 'resume')
```

The example describes separate sequential requests, not calls to run together. Request IDs must increase within the state machine lifetime. Other owners/epochs, old IDs and concurrent requests are rejected before calling X4. The save slot must match `save_ddd`. The caller's two boolean save assertions are **not verified by Lua**: before submitting, its supervisor must ensure the process has no other save initiators and that the complete slot inventory is empty in the private profile. Do not apply this to an existing or normal save. No filesystem or slot-ownership verification is performed here.

Pause succeeds only after `IsGamePaused()` is true and at least two observations, separated by the configured positive real-time interval, show an unchanged game clock. Resume succeeds only after `IsGamePaused()` becomes false and the observed game clock advances. These are bounded UI observations, not proof that every native worker is quiescent. A missing callback or paused UI loop can leave a request pending; the supervisor needs its own deadline and process fencing.

Save is accepted only after the state machine itself confirmed pause, the game remains paused at the same game time, `IsSavingPossible(false)` returns true, and the owner asserts its exclusive/slot preconditions. In default mode, no earlier save may have been attempted in the process. Each accepted engine call happens at most once. `gameSaved(true)` is recorded, but only the next update with the pause still confirmed produces a report with `status='native_event_only'` and `reason='file_verification_required'`. A failed/duplicate/unexpected event, pause loss, timer regression, deadline, callback failure or engine error faults the instance; a fault cannot be reset in Lua. Because the X4 event supplies no request ID or slot, it is not independently attributable if another actor can save. After any uncertainty, the supervisor must fence the old operation and process before creating another instance; ignoring a late event alone is insufficient.

In repeat mode the state machine derives a distinct title from the world epoch
and request ID, includes it and the slot in the native-event receipt, and will
not accept another action until `state:confirm_save(owner, world_epoch,
request_id, true)`. Before making that assertion the supervisor must verify the
actual file, its title and bytes, durably publish the checkpoint, and verify
that the process remains paused. Lua cannot verify the filesystem or the
supervisor's assertion. A verified previously used slot may be requested again
only with `overwrite_verified_owned_slot=true`; a new slot still requires
`empty_owned_slot=true`. The supervisor remains responsible for exclusive
ownership and actual slot contents. A false verification, lost pause, or foreign
save event faults the state. The Lua tests use doubles; the native three-save
experiment used a separate test supervisor and did not connect this option to
the coordinator.

The report callback receives `{world_epoch, request_id, operation, status, reason}`. An exception from the callback faults the instance. Pause/resume reports use `status='confirmed'`; a native save event is never `confirmed`. A supervisor for `WorldCoordinator` must wait asynchronously without blocking the X4 UI thread and make its synchronous `save()` return only the exact completed, stable save. The coordinator then publishes it through `CheckpointStore` and, if the adapter supplies `checkpoint_published(checkpoint)`, invokes that callback before acknowledging the save or proceeding. The callback can bind the published checkpoint to the waiting native request and issue `confirm_save`; it must explicitly return `True` after successful confirmation. An exception or any other return value faults the coordinator while retaining the published checkpoint. A matching receipt must identify the same owner, epoch and request, and an error/timeout must fail the coordinator closed. The experimental local bridge implements this path for a disposable Linux X4 process; see its separate documentation for the exact test scope. `WorldCoordinator.mark_loaded(..., trusted_confirmation=true)` still requires an independent native load receipt; delivery of bytes is not readiness.

Open native questions include whether `IsSavingPossible(false)` succeeds once already paused, the precise behavior of nested pause ownership, the availability of UI callbacks while paused in this integration, and the meaning of `gameSaved` under concurrent or delayed saves. The old pristine-world capture checked saving availability **before** pausing; its success does not answer the first question. No Internet, multi-client or persistent-world outcome follows from this prototype.
