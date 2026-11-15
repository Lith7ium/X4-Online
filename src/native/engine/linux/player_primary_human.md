# Finite human primary FIRE replay

Default off. `--player-primary-human` requires `--player-primary-capture`, active
flight cursor, resident dispatch, independent T40 physics and 180..900 session
frames. It is mutually exclusive with `--player-primary-trigger-experiment`.
Run only both local clients from the same sealed bundle. External relay mode is
refused: existing stock-v3 neutral records do not negotiate primary capability.

The capture adapter suppresses the exact native fire handlers and owns focus,
context loss and release-to-rearm. Its exact-once seal precedes an immutable
`player_primary_capture_sample(generation, &held)` read. The downstream record
sets only existing stock-v3 FIRE bit 16. Secondary bit 32 stays unsupported.
Neither native handler ledgers nor shared packet layout change here.

Both delayed records pass canonical/slot/capture-tick/local-echo and semantic
checks before either player callback. Prepare stages independent wants; native
primary apply consumes them only after both slot updates. Remote records are
never masked by this process's focus. The final capture forces FIRE=0 so the
finite terminal drain uses the same delayed transport as an ordinary release.
This drain is a deliberate experiment boundary, not an instantaneous local
simulation update.

Existing pinned Mindless-controller construction, initial neutral-gun admission,
both-group preflight, retain/install, operational and ownership revalidation
remain in force. Installation callbacks and failure can already have effects.
Native references/controllers stay resident until disposable process exit; no
uninstall, rollback or normal resume is provided. Receipts distinguish each
slot's desired trigger from the later gun firing byte. Firing bytes do not prove
projectile creation, ammunition consumption, heat, hits or combat determinism.

Integration order: capture commit first, then this downstream change. Shared
files are `gate_stock_keyboard_replay.h`, `linux_gate_live.py`, and the capture
request's script-exclusion predicate. The source receipt layer is version 21,
wrapping capture version 20. Capture-only defaults and script-v1 remain usable.

## Native validation status, 15 November 2026

The first capture-only native attempt stopped on both peers at
`fire_capture_tree`, before any planned trigger input. The retained receipt
does not identify which registration predicate failed. Focused source tests do
not replace this missing native admission/input evidence. Human FIRE replay,
release-to-rearm in a real game and combat remain unvalidated.
