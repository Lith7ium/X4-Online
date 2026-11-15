# Isolated one-fixture MD velocity experiment

This opt-in Linux diagnostic uses the existing disposable fixture-warp runner and
one saved MD fixture reference. It is not enabled by the multiplayer code. It
may collide, fail or crash, and it does not establish
collision clearance or atomicity. Do not use a normal profile or save.

The first fixture is restored from the validated 12-ship snapshot. The UI checks
that it is a live ship, outside the local player context, undocked, not being
docked or internally stored, and remains in the same sector and zone. The MD
cue repeats its own checks immediately before each operation. Neither check is
an engine lock and the runtime-to-saved-ID mapping is not independently proven.
A baseline measured for at least one real-time second must move at most 0.5 m,
or no setter is requested. Then the cue requests `<set_object_velocity>` with
linear x = `10m / 1s`, y = z = `0m / 1s`, and `constantvel=true`. After two
position readings at least one and two real-time seconds after acknowledgment,
a second one-shot cue requests a zero linear vector with `constantvel=false`.
The UI then observes positions again after one and two seconds. Failure, invalid
state, a missing receipt or timeout ends the owned disposable process; if a
failure prevents the stop request, process termination and discarding the copied
snapshot are the containment, not a verified reset.

The supervisor demands ordered receipts, a quiet baseline, 2–50 m displacement
in each of two motion intervals, and at most 1 m between the two post-reset
observations. Positions come from X4's `GetObjectPositionInSector`; the test
has **no native velocity-vector readback**. Thus a pass would show movement and
subsequent near-stationarity under these conditions, not prove the actual vector,
its coordinate axes or units, exact velocity restoration, game-time speed, or
that all observed movement was caused only by the setter. Acknowledgments mean
that the cue reached the action; they do not prove immediate physics completion.
The original velocity and constant-velocity mode are not read or restored: the
reset explicitly requests zero and false. Neither this nor synthetic tests show
anything about LAN smoothing, other players, persistence, or multiplayer design.

The runner requires an existing private `.local` fixture bundle with matching
snapshot digest; it copies the save into a fresh isolated profile, mounts it
read-only to the pinned X4 executable, checks Steam ownership, refuses an
existing X4 process and stops only its own process group. See
[the warp experiment](AUTHORITY-FIXTURE-WARP-EXPERIMENT.md) for the underlying
isolation and saved-reference limitations. The user must explicitly choose a
fresh output directory and invoke the test after closing X4:

```sh
python3 tools/dev/authority_fixture_velocity_live.py --game /path/to/X4 \
  --bundle .local/authority-fleet-05 --out .local/authority-fixture-velocity-01 \
  --display :0
```

The private output directory retains raw observations and a result. Focused
synthetic checks, including the existing warp runner, are run with
`python3 -m unittest discover -s tests -p 'test_authority_fixture*live.py' -v`.
Mock Lua and XML checks do not validate actual X4 behavior.

## Native observation

One isolated Linux X4 run completed successfully on 2026-11-15. The baseline
displacement was 0 m; the two motion intervals measured approximately 10.05 m
and 9.99 m; the interval after reset measured 0 m. The measured interval was
approximately one real-time second. The test stopped its own processes and
reported unchanged Steam identity. This is a single-fixture observation subject
to the limitations above; it does not demonstrate networked velocity, motion
smoothing, cross-platform behavior, or fleet-scale synchronization.
