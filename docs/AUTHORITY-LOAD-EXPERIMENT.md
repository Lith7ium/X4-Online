# Isolated authority checkpoint load experiment

`tools/dev/authority_load_live.py` is a separate, explicitly invoked Linux-only
experiment. It is not a multiplayer loader, server implementation or admission
protocol. Importing it never starts X4. It requires an already completed
`authority_control_live.py` run or an already completed two-cycle
`authority_cycle_live.py` run, and the checkpoint selected by the appropriate
`CURRENT` pointer. Close all X4 processes first. It uses a newly created private profile
under this checkout's `.local` and refuses the player's normal save locations.

The runner independently verifies the checkpoint's manifest, digest, gzip and
XML; checks the source control receipt and completed process cleanup; stages it
into the new profile's only save slot; checks the copied SHA-256; and overlays
that file read-only in the X4 namespace. It requires the source and destination
profile extension lists to match. It pins the current X4 executable and uses
only the locally installed `ego_dlc_*` allowlist. Matching extension IDs do not
prove that DLC contents or versions stayed unchanged since the source run.
For a two-cycle run, it accepts only `checkpoints/cycle-2` as the source: it
revalidates both cycle checkpoints against their own `CURRENT` pointers, their
private cycle ID and saved titles, their ordered save times, the cycle result,
and the complete ordered cycle log. The first cycle cannot be selected as the
load source. Source receipts and save identity remain local to the private run.

The UI probe requests `save_009` from the start menu after save-list refresh.
X4 recreates the UI on load: the external log watcher requires exactly ordered
`ARMED`, `REQUEST`, `READY`, and `ADVANCED` receipts, including increasing
finite game times. Once a player is valid, a paused loaded session is unpaused
in this disposable profile solely to measure progress. A timeout, missing,
duplicated or out-of-order receipt, incorrect profile, absent slot, changed
checkpoint or cleanup failure makes the experiment fail. This test does not
create or expect the LAN battle fixtures or log saved object identities.

The load result also requires the first observed loaded game time to be no
earlier than the checkpoint's `info/game @time`, allowing one millisecond for
save rounding. Both values are recorded on success and on comparison failure.
This is an empirically supported lower bound, not an exact-load identity test:
eleven earlier private Linux capture logs on the same pinned executable recorded
`GetCurrentGameTime()` at both save request and save completion, and their saved
XML time differed by at most 0.000407 seconds. Those eleven observations all
used early game times around seven seconds. They do not establish behavior for
all time ranges or platforms. No upper limit is imposed: the time spent loading
and entering the world is not known in advance. Consequently, a wrong older
world that advances sufficiently before observation might satisfy the bound.

After checking that the prior `result.json` records successful cleanup, use the
checkpoint ID from that private result. Set the game path and display to the
local installation and desktop; choose a new output directory each time:

```sh
python3 tools/dev/authority_load_live.py \
  --game /path/to/X4 --store .local/authority-control-01/checkpoints \
  --checkpoint-id checkpoint-REPLACE_WITH_SOURCE_ID \
  --out .local/authority-load-01 --display :0
```

For a completed two-cycle run, use its `checkpoints/cycle-2` directory as
`--store` and the second cycle's checkpoint ID from that run's `result.json`.

The process is started only by an explicit command. The script retains private
logs, staged save and result under the 0700 output directory, including on
failure. It uses the existing owned-process and lock cleanup. No network
connection or personal save is required by this test.

A successful result would establish that the UI requested the staged slot and
then observed a valid player with advancing game time. The file's hash and
read-only mount provide strong supporting evidence, but do not directly attest
which file bytes X4 consumed. The result does not establish recovery of all
world state, a new join, multi-client synchronization, platform interoperability
or save distribution. The exact profile-path convention, UI callback lifecycle,
read-only-file compatibility and X4 load/clock behavior remain native-test
questions until actually executed. The comparison's empirical assumptions must
be revisited if the executable or target platform changes.

Synthetic coverage: `python3 -m unittest discover -s tests -p
"test_authority_load_live.py" -v`. These tests use temporary files and Lua
doubles; they do not launch X4.
