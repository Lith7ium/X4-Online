# Isolated single-X4 process measurement

`authority_fixture_single_running_measure_live.py` is an explicit Linux-only
experiment. It imports without starting a game. Run it only inside the separately
reviewed private display/process scope, with a fresh `.local` output. It accepts
only the pinned, previously confirmed Rejoin fixture checkpoint. The source
supervisor must be stopped and no external writer may modify its files.

The existing recovery owner copies the checkpoint, checks its saved marker,
waits for a pause, and guards the process, Steam identity and private files. The
new local UDP owner binds to the owned X4 process and requests one resume. It
then measures the game and Python supervisor separately over 60–120 seconds,
with fresh native game-time receipts before and after. The game save directory
is read-only inside the X4 namespace; no save is requested. Recovery stops the
owned process, verifies cleanup and rechecks the staged save and pinned source.
A failed or timed-out resume may already have occurred; cleanup, not a presumed
rollback, is the remedy.

The game-time checks establish advancement between endpoints, not uninterrupted
simulation or byte-exact save consumption. The measurement includes recovery
supervisor checks and instrumentation overhead: protected small configuration,
Lua and MD files are hashed during the window; the large staged save is checked
before and after it, not repeatedly within it. `/proc` reports per-thread and
process CPU and resident memory; one logical CPU is 100%, and RSS includes
shared pages. The separate supervisor reading is the Python recovery runner only and includes
its measurement work. Cage, Xwayland, the scope launcher and other helper
processes are not included in that supervisor value.
Process/thread lifetimes and sampled intervals are reported; short-lived threads
can be missed. FPS, frametimes, Windows, WAN and gameplay are not measured.

Compare against the two-X4 run only when checkpoint, display, startup conditions
and measurement duration match. A shared checkpoint, 800×600 resolution and the same GPU do not establish an
identical camera, scene, in-game time or diagnostic load. Record and explain
the other run's guard and network activity. Results are not a clean estimate of
multiplayer overhead when those conditions differ. No native test of this new
runner has yet been made.
