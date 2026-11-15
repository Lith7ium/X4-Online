# Isolated NPC movement signal experiment

This is a diagnostic, not multiplayer or an approved control mechanism. Each
invocation runs **one** arm on a fresh disposable Linux profile. Run the
control and treatment sequentially using different, new output directories.
Both use the same pinned archived checkpoint, registry epoch, slot 2, seed,
profile construction, zero-velocity intervention and release. The existing
archive verification and process ownership checks apply. Exact engine loading
of the staged file and runtime-to-save actor binding remain unproven; the
archive marker and validated registry references provide narrower evidence.

After loading, the selected ship must have the recorded sector, undocked zone
parent, existing pilot and an active order. The phases are three one-second
baseline samples, a zero linear velocity setter with `constantvel=true`, three
one-second samples, release with `constantvel=false` and no vector children,
five samples separated by at least five game seconds, then the decision and
five further five-second samples. Both arms have the same timing protocol;
actual game times are recorded and may differ because independent simulations
and dispatches are not deterministic. The process is paused and cleaned up;
there is no save.

Control issues no signal. Treatment sends exactly one `patch_reset_moveto`
signal to the guarded pilot only if the same order ID and state still exist at
the decision; otherwise `skipped_order` is recorded and observation continues.
Signal receipt proves that the MD action was reached, not that an AI handler
was active or executed. The internal handler found in the installed scripts
stops and restarts movement and may affect script state. This is not evidence
of a lossless restoration or general NPC applicability.

Every sample records position, game/real times and reported order ID/state;
order changes after intervention are retained as observations. An initial
order change before intervention, lost actor/pilot/sector/zone binding,
docking, invalid numbers, missing or duplicate receipts, pause loss, timeouts
or process/cleanup failures make the affected arm fail. Results and logs must
be inspected for **both** completed arms and for the `sent` outcome before
interpreting a signal comparison. Same order ID/state does not establish the
same order instance, parameters or queue, and the prior constant-velocity state
and native velocity are not read back. A changed trajectory in one run is an
association, not conclusive causation.

For an explicitly authorized native investigation, use the runner's `--help`
and pass the same `--game` and `--display` in each invocation, once with
`--mode control` and once with `--mode treatment`. Use two separate `.local`
output directories outside the source experiment tree. Preparing and testing
the runner does not itself start X4.
