# Experimental census runtime read

`authority_census_runtime_read_live.py` is an opt-in, isolated Linux diagnostic
for the pinned `authority-registry-census-01` checkpoint. It is not a server,
client admission path, or multiplayer protocol. It has not yet been exercised
in X4. The wrapper reuses the existing isolated load supervisor, verifies the
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

Only the synthetic tests have run:

```sh
python3 -m unittest tests.test_authority_census_runtime_read
```

These tests use Lua and filesystem doubles, including a 105-entry example;
they do not execute X4 MD semantics, demonstrate saved-register runtime binding
or establish native reliability. A native test requires a reviewed isolated
headless run and can take substantial time for the full register.
