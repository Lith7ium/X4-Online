# Persisted references to ships created after startup

`tools/dev/authority_identity_live.py` is an opt-in Linux diagnostic using the
existing disposable save and read-only reload harnesses. It starts no game on
import. In the first isolated X4 process, the test mission creates two ships
after startup and keeps their object references in an MD cue list. The probe
assigns distinct names, waits until both names and the expected ship macro are
observable, and only then permits the isolated save. After the first process
has stopped, a second isolated process loads the verified save read-only and
asks the restored cue to emit both object references again. The probe checks
that both refer to distinct operational objects with the expected names and
macro. The game installation and the player's normal profiles are not changed.

One run on 2026-11-15 completed both phases. The two expected names and macro
were observed again after reload, and both runtime IDs differed between the
two processes. Both owned processes were cleaned up. This supports persistence
of these two MD-held references across this save/reload; the differing runtime
IDs show why those local IDs cannot simply serve as durable network IDs.

This is a bounded fixture observation. The names are distinguishing evidence,
not an independently verified globally unique identity, and this diagnostic
does not observe every ship created by X4, destruction or recreation, object
binding between simultaneous clients, full world state, Windows, or gameplay.
It does not select a production identity architecture. The saved references
and private runtime IDs remain in the local experimental output.

Run only in an isolated desktop session with a fresh private output and the
existing pinned X4 build:

```sh
python tools/dev/authority_identity_live.py --game /path/to/X4 \
  --out .local/authority-identity-experiment --display :2 --timeout 600
```

The XML fixture was validated against the locally available X4 MD schema.
`tests/test_authority_identity_live.py` covers receipt parsing and the Lua
helper with doubles; those tests do not launch X4.
