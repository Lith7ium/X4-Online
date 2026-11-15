# Isolated one-fixture MD warp experiment

This is an explicitly invoked, single-process Linux diagnostic. It performs one
engine-managed MD `<warp>` of `X4LAN_NativeGate.Spawn.$ships.{1}` from a verified
fixture snapshot, followed by immediate and delayed position observations. It
is not registered with product code or multiplayer. No X4 process is started by
importing the runner. The experiment may collide or crash; it does not assert
collision clearance or atomicity. Use only a disposable profile and snapshot.

The source must be an existing private native-gate bundle beneath `.local` with
matching snapshot digest in its manifest and file inventory. The runner copies
that snapshot into a fresh private profile, checks the digest, validates all 12
saved fixture-list entries and their component records, and mounts the new save
file read-only to X4. It pins the Linux executable, isolates HOME/extensions,
checks Steam ownership and cleans up only its own process group and lock.
Existing X4 processes prevent the run. It never saves during the test.

On load, the UI requests the existing `RestoreActors` cue. The new cue addresses
only the saved MD list's first reference, checks that it matches the UI's
returned object, the selected zone/sector, a live ship, local player exclusions,
dock and storage state, then makes one sector-space warp ten metres in +X. The
UI independently checks component validity, local player contexts, docking and
storage flags, and sector/zone before and after. The MD Parent comparison is
performed immediately before the warp; it is not a proven engine lock. There is
no velocity setter, dynamic candidate selection, or retry after rejection.

The supervisor requires ordered load, pre-state, request, MD acknowledgment,
first readback and delayed readback. Both readbacks must report 5–15 m movement;
first position must lie within 1 m of the 10 m target, and the delayed position
within 3 m, at least one real-time second after acknowledgment. Lost/duplicate
receipts, actor or sector/zone changes, invalid values and a timeout fail the
experiment. A sector-based warp can create or change a zone; that makes this
experiment fail rather than silently weakening the frame check.

Without the native gate, this test cannot independently map the runtime handle
back to the saved component ID. It validates the saved reference list and asks
X4 to restore the first reference, but `runtime_saved_id_proven` remains false
in the result. This is not evidence about other player representations,
collision freedom, persistent world state, all ships or multiplayer.

Run only on explicit request after closing X4, choosing a fresh output directory:

```sh
python3 tools/dev/authority_fixture_warp_live.py --game /path/to/X4 \
  --bundle .local/authority-fleet-05 --out .local/authority-fixture-warp-01 --display :0
```

The runner retains private raw measurements and result under the 0700 run
directory. Focused synthetic checks: `python3 -m unittest discover -s tests -p
"test_authority_fixture_warp_live.py" -v`. Their Lua mocks and XML checks do not
prove actual X4 behavior.

## First native observation

One isolated Linux run reached all ordered receipts and kept the selected
fixture's sector and zone unchanged at both readbacks. The MD cue acknowledged
the request. The first UI readback still showed the original position: its
displacement was 0 m and its target error 10 m. At 1.005 seconds after the
acknowledgment, the readback showed a displacement of 10 m and a target error of
0 m. The runner therefore reported **failure**, as required by its previously
defined immediate-readback criterion. Its private result and raw log remain
unchanged; the late observation does not retroactively make the strict test
pass. The owned process group was cleaned up and the checked Steam identity did
not change.

This observation supports delayed application in this one case, rather than
immediate visibility after the cue's acknowledgment. It does not establish when
the engine applied the warp, whether the acknowledgment is a completion signal,
or how a moving ship, another client, velocity, collision handling, or network
updates behave. No second native run was performed.
