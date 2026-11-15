# Isolated single-X4 control experiment

`tools/dev/authority_control_live.py` is an explicit, Linux-only diagnostic. It reuses the private case, executable pin, Steam identity checks, read-only game view and owned-process cleanup from `linux_snapshot_capture.py`. It does **not** run the lockstep gate: that gate requires game speed 1.0 and stops with reason 3 when X4 pauses for a save. The experiment starts a new disposable `custom_creative` world in profile 45841, not an existing player save.

When explicitly invoked with a running Steam client, no other X4 instance, a local X11 display, readable `XAUTHORITY`, bubblewrap and a C compiler, it:

1. Creates a new private output and an empty save directory under `.local`.
2. Installs only the opted-in control probe into the private extension view. The old capture script and battle fixture are removed from that new view. It does not alter the installed game or normal profile.
3. Requests one pause and waits for the control state machine's observed pause confirmation. It checks the isolated save list and calls `SaveGame` exactly once for the empty `save_009` slot.
4. Waits for the native `gameSaved` event. The Python supervisor then copies the gzip save into a `CheckpointStore`, verifies the entire gzip/XML and hash, and independently reads the committed checkpoint back.
5. Only after verification, sends a one-run, lease-bound loopback signal to that process. The probe rechecks pause and game time before requesting resume; it requires observed game-time progress afterward. The runner then stops only its owned test process and retains private evidence.

The signal is **only a local test bridge**, not an Internet or production multiplayer protocol. Its lease is private and removed from the test config during cleanup. A control timeout, partial/missing save, invalid file, lost pause, unexpected/duplicate receipt, process failure or changed Steam identity fails the experiment. Log receipts are collected incrementally with bounded memory and a size limit; old markers are not discarded on log growth.

This prepares the experiment but does not run it. In particular, `IsSavingPossible(false)` in the already paused game may refuse the save, and the availability of update callbacks while paused must be established by an actual isolated native run. A successful run would prove only one local pause/save/verification/resume cycle, not repeated campaign saves, reconnects, two-client gameplay, Internet operation or Windows behavior.
