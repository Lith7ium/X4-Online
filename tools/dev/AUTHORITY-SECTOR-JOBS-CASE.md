# Isolated sector jobs control/treatment case

This is a default-off experiment built on `authority_sector_read_live.py`.
One isolated native pair is recorded below. Invoke **one** explicit
`--mode control` or `--mode treatment` per fresh `--out` directory. Both use
fixture slot 2 from the same fixed archived checkpoint and its independent
provenance checks. They use separate disposable processes and profiles, not a
multiplayer session. Normal profiles and saves are outside the experiment.

The existing load callback is the sole update owner. It waits for the existing
marker and paused slot-read checks, then passes the locally checked actor and
sector to the private case. The Begin game time must equal the earlier paused
read's game time; this comparison does not establish a continuous pause. After two equal game-time samples at least 0.1
engine-real-time seconds apart while paused, it issues one Begin. Control does
not call the jobs setter; treatment executes `set_space_jobs_allowed` with
`allow=false` on the checked sector. A `Began` receipt means the MD script took
the relevant branch: it does **not** prove that the sector's effective jobs
permission changed or stayed changed.

Only after the Begin response does the case request one resume and wait for
unpaused game-time progress. It makes six serialized guarded Sample requests
spread over at least `--min-game` seconds of simulation, default 5 and limited
to 1–30, with a 40-second engine-real-time deadline from case start and a
5-second per-request deadline. Each reply carries the request ID, order type and
MD-formatted local actor hex. Lua compares that exact uint64 to the local FFI
actor before reading its position; mismatches, duplicate or stale replies,
invalid actor/sector, loss of the expected pause state and timeout fail closed.
The samples report the MD guard's same-pilot check and order type/state, the
game times immediately before and after the FFI position read, and
`GetCurRealTime` as an engine clock, not OS-monotonic time. The case
then requests pause once and confirms pause with two equal game-time samples at
least 0.1 engine-real-time seconds apart. A failure after resume causes the
inherited runner to terminate its owned process and discard the disposable
world; it does not save or admit a client. Unexpected MD refusal has the same
result. No ship, position or order is created or changed by the case.

Each sample's MD pilot/order guard and subsequent FFI position read are not
atomic. The order ID identifies a type, not a particular order instance. The
local actor comparison is not cross-process identity and does not independently
bind the runtime actor to the saved XML actor. Individual pause checks do not
prove continuous pause, marker inspection does not prove exact loaded bytes,
and six samples in a short simulation window cannot establish AI causation,
job-suppression effectiveness, coverage, smoothness, multiplayer, or gameplay.
A treatment Begin modifies this disposable world's jobs setting; no reset is
attempted and the profile is never reused.

Each output is one observation, not a general A/B conclusion. Both modes must
be run separately from the same confirmed archive with fresh output paths. The general launch,
resource ownership, cleanup and signal-race limitations remain those described
in `AUTHORITY-SECTOR-READ-PREFLIGHT.md`. Run
`python -m unittest discover -s tests -p 'test_authority_sector_jobs_case.py' -v`
for the synthetic callback, uint64, XML and overlay tests without starting X4.

## One native pair

`.local/authority-sector-jobs-control-01` and
`.local/authority-sector-jobs-treatment-01` each reported `success=true` from
separate disposable Linux X4 processes. Their load receipts identify the same
archived checkpoint and both began at game time `3.014` on slot 2. Each reported
the same pilot and a `Patrol` order in `started` state across six samples,
then a confirmed final pause and no remaining owned processes. Neither requested
a checkpoint. Both engine logs also record failure to write the deliberately
read-only `config.xml`.

The treatment log contains `BEGAN mode=treatment`; in the staged MD script this
receipt follows the treatment branch's `set_space_jobs_allowed ... allow=false`
call. This is evidence that the script reached that setter path, not independent
confirmation of effective sector permission or inherited settings of child
spaces. Control did not request a jobs change.

For the FFI positions from the first through sixth running sample, the Euclidean
endpoint displacement was approximately 1,410.55 game-coordinate units in
control (game times `3.85676` to `8.02537`) and 1,336.65 in treatment
(`3.86153` to `8.02910`). These are endpoint differences, not path lengths or
proof of their cause. In this one short pair, a position change was reported in
both modes; the result cannot establish whether jobs were effectively disabled,
whether AI or any particular subsystem caused movement, or behavior elsewhere
in the universe. The actor/clock/atomicity and load-byte limitations above apply.
