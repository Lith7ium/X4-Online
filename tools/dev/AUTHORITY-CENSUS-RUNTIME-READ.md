# Experimental census runtime read

`authority_census_runtime_read_live.py` is an opt-in, isolated Linux diagnostic
for the pinned `authority-registry-census-01` checkpoint. It is not a server,
client admission path, or multiplayer protocol. The wrapper reuses the existing
isolated load supervisor, verifies the
archived checkpoint and origin scripts, loads a private copy, observes the saved
marker and requests pause before invoking its one update owner.
The archived identity fixture's original MD script is also installed unchanged
to preserve the saved extension state; its ship-creation cue requires a separate
UI event, which this probe never sends.

The default requests every saved registry index, 1 through 10,054. `--limit`
can select a smaller initial prefix. Each index has a single correlated MD
request in flight. An operational ship with a sector is converted to local
64-bit handles and checked with the X4 API. The diagnostic records finite X4
position coordinates in that local sector's coordinate frame; it also counts
distinct local sectors. Registry refusal, a mismatched correlation, duplicated
local ship handles among `ok` MD responses, changed game time or a lost observed
pause fails the run. Other responses carry no ship handle, so this is not a
duplicate check over all entries.
`unavailable`, `no_sector` and `local_invalid` are counted separately; those
categories are observations at read time, not proof of destruction.
Docked or internally stored ships are counted separately before any position
FFI call; their position semantics have not been established by this probe.
An orderly complete scan can succeed even if no position was read; in that
case `position_observation_conclusive` is false.

The log contains a local sector handle solely to interpret the local position.
Neither that handle nor any other local actor identifier is a network identity.
There is no network motion stream or velocity, no independently verified
runtime-to-save object identity, and no claim of atomic world sampling or
universe-wide coverage. The results do not test either player's gameplay.
Pause checks are sampled rather than continuous. The original archive is not
modified; the staged save is mounted read-only in a disposable profile.

The first native run, `.local/authority-census-runtime-read-01`, failed with
`local evidence file changed while reading`. Its retained `result.json` remains
failed. Its final log contains 1,815 consecutive rows, including 1,813 finite
positions from 74 local sector handles and two docked/stored entries. There was
no completion or final pause receipt, so this is partial evidence, not a
successful scan. The error does not identify the file; a log append during the
strict snapshot read is a plausible but unconfirmed cause.

The log watcher now retries a specifically typed observed growth case. It checks
the captured inode, size and previously accepted prefix before discarding the
unstable capture; a changed, replaced, truncated or missing previously observed
log fails. Protected files and the final stopped-process log remain subject to
the strict stable-file read. As before, these are sampled checks and cannot rule
out changes that are made and reversed between observations. Focused synthetic checks can be run with:

```sh
python3 -m unittest tests.test_authority_census_runtime_read
```

These tests use Lua and filesystem doubles, including a 105-entry example;
they do not execute X4 MD semantics, demonstrate saved-register runtime binding
or establish native reliability. A native test requires a reviewed isolated
headless run and can take substantial time for the full register.

On 2026-11-15, the revised watcher completed one isolated native Linux run over
all 10,054 indices in the archived checkpoint. It recorded 10,052 finite
positions across 140 local sector handles and classified two entries as docked
or internally stored, without reading their positions. It reported zero
unavailable, missing-sector and local-invalid entries, observed pause at the
checkpoints and reported no remaining owned processes after cleanup. A separate
read-only review recounted the consecutive rows, finite positions, categories,
sector handles and load/marker/completion/pause order in the retained log and
matched them to the result. This is a
paused local read of this particular registry, not a live stream, independently
proved runtime-to-save binding, complete universe coverage, a native velocity
measurement, or a multiplayer test.
