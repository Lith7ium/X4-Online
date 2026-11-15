# Experimental local X4 control

This is a disabled-by-default prototype for an **isolated test profile**, without a network listener, launcher, save transfer, client admission, automatic event registration or game loop. It does not call `QuitGame`, `LoadGame` or change the user's normal saves. It is not connected to `WorldCoordinator`. The included tests use injected Lua doubles; this code has not been run in X4 or validated on Windows.

The approach reuses the earlier LAN experiment's `IsGamePaused`, `Pause`, `IsSavingPossible(false)`, `SaveGame` and `gameSaved` mechanisms. It also uses `Unpause` and observed game time. Unlike the earlier one-time pristine-world capture, it never exits X4 and never declares a save complete from an event alone.

## Explicit integration contract

`control_state.lua` exposes the inert factory as `X4LAN_AUTHORITY_CONTROL_STATE` for X4 UI loading; it contains a pure state machine. `new({enabled=false}, ...)`, an absent config, or any value other than boolean `true` returns disabled without touching the engine. An enabled configuration supplies `owner`, `world_epoch`, `timeout_seconds` (default 30), and `pause_settle_seconds` (default 0.1). Owner and epoch are local fencing labels, **not authentication**. The caller must exclusively own this specific X4 process and serialize every call. Creating another state machine for the same process would defeat the one-save fence; it must be forbidden by the future supervisor.
The one-save-per-process rule is a temporary diagnostic restriction, not a design for a persistent campaign: repeated joins and last-player departures require repeated saves. Before that goal can work, a future implementation must establish a safe, verified multi-save lifecycle and fencing strategy.

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

Save is accepted only after the state machine itself confirmed pause, the game remains paused at the same game time, `IsSavingPossible(false)` returns true, the owner asserts its exclusive/empty-slot preconditions, and no earlier save was attempted in this process. The engine call happens at most once. `gameSaved(true)` is recorded, but only the next update with the pause still confirmed produces a report with `status='native_event_only'` and `reason='file_verification_required'`. A failed/duplicate/unexpected event, pause loss, timer regression, deadline, callback failure or engine error faults the instance; a fault cannot be reset in Lua. Because the X4 event supplies no request ID or slot, it is not independently attributable if another actor can save. After any uncertainty, the supervisor must fence the old operation and process before creating another instance; ignoring a late event alone is insufficient.

The report callback receives `{world_epoch, request_id, operation, status, reason}`. An exception from the callback faults the instance. Pause/resume reports use `status='confirmed'`; a native save event is never `confirmed`. For `WorldCoordinator`, a future supervisor must wait asynchronously without blocking the X4 UI thread, validate the exact newly created save, ensure completion and stability, then publish it through `CheckpointStore` before its synchronous `save()` returns. A matching receipt must identify the same owner, epoch and request, and an error/timeout must fail the coordinator closed. `WorldCoordinator.mark_loaded(..., trusted_confirmation=true)` still requires an independent native load receipt; delivery of bytes is not readiness.

Open native questions include whether `IsSavingPossible(false)` succeeds once already paused, the precise behavior of nested pause ownership, the availability of UI callbacks while paused in this integration, and the meaning of `gameSaved` under concurrent or delayed saves. The old pristine-world capture checked saving availability **before** pausing; its success does not answer the first question. No Internet, multi-client or persistent-world outcome follows from this prototype.
