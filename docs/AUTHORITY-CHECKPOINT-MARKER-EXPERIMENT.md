# Checkpoint marker after a native load

`tools/dev/authority_checkpoint_marker_live.py` is an opt-in extension of the
existing isolated two-X4 diagnostic. It generates a fresh marker and places it
in server-side MD state before the verified checkpoint. The load-event flag is
set to false before saving. The client is not given the marker in configuration
or in its inspect request. A root MD cue listening for `event_game_loaded` sets
the flag after X4's load event; the client then explicitly inspects the saved
state and reports its marker. The supervisor compares that receipt with the
server marker and the single verified checkpoint offer/load attempt. The
existing harness also checks checkpoint transfer, isolated process continuity,
pause observation, and two saved fixture references. No client is admitted.

X4's local MD schema describes `event_game_loaded` as occurring when loading a
savegame is complete. The event does not supply a path or file hash. The
explicit marker query avoids relying on a Lua callback that could be missed
while the UI reloads. The load listener is a root cue saved in the test world;
the schema warns that a newly added non-root cue can miss the first load event.

This is an experiment, not a production trust mechanism: a matching marker is
evidence of the expected saved MD state following an engine-reported load. It
does not cryptographically prove which bytes X4 consumed, the state of all
world objects, honest client behavior, gameplay, Windows, or Internet transport.
One native attempt failed because the client queried the marker while X4 was
still in the second loading pass; the player-valid signal alone was too early.
The probe retries an explicit missing marker/load-event response at bounded
intervals for up to 60 seconds. An unanswered inspect request is not retried;
the experiment instead fails when its deadline expires. Only a
successful inspect after the MD load event is accepted. In a second isolated
Linux/Linux run on 2026-11-15, the client returned the same marker after the
load event, the saved fixture checks and checkpoint transfer passed, and the
owned processes were cleaned up. No client was admitted. This supports the
marker association under the experiment's controlled conditions, subject to
the limitations above. Runtime output contains the marker and belongs only in
the private diagnostic directory.

The command requires a fresh `.local` output path, the pinned local Linux X4
installation, Bubblewrap, and a separately provisioned virtual X11 display:

```sh
python tools/dev/authority_checkpoint_marker_live.py --game /path/to/X4 \
  --out .local/checkpoint-marker-experiment --display :2 --timeout 600
```
