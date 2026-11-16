# Motion-buffer calibration: offline preparation only

`authority_motion_calibration_offline.lua` is a default-off synthetic state
machine. It has **no X4 binding, process launcher, MD script or native command**;
`native_ready()` always returns false. In particular, caller-supplied boolean
claims in fake observations do not establish pilot absence, no autonomous
orders, frame alignment, a clear volume or any other property of a real game
object. Do not connect it to X4 by supplying fabricated positive guards.

The test loads the real `src/authority/lua/motion_buffer.lua`, generates two
small deterministic *synthetic source samples* in one named frame and warms
the actual render clock. It requests a bounded pose from an interpolated
render, waits for a correlated fake receipt and readback, then freshly renders
again and requests only a bounded linear velocity; no new pose is written
during the two subsequent position observations. The result records synthetic
source/arrival/render times, phase, pose, optional derivative, request/receipt
and readback times in both fake real and fake game clocks. The first rendering
has unknown velocity (`nil`), which is neither treated as zero nor sent.
Only interpolated/extrapolated rates are accepted; a frozen zero is known in
the buffer but not used by this experiment. The supplied derivative remains a
rate per observer-clock second, not evidence of X4's velocity unit or frame.

Each operation uses fake snapshots requiring unchanged actor, sector, parent,
epoch and frame, no pause, monotonic clocks and measured 0.95–1.05 game/real
progress over a bounded interval. Failure, ambiguous dispatch, incorrect,
duplicate or late receipt, guard/clock change or timeout permanently faults
that instance; there is no retry. `mutation_attempted()` changes before a
fake dispatch, because a throwing callback might already have applied a change.
The report callback is invoked before the last guard: its argument is only a
provisional intent and the caller may consume it only after that tick returns
true and the state is `done`. A later fault invalidates any provisional intent.
The final result does not prove native velocity readback or restoration.
These guards test control flow, not the validity or atomicity of X4 getters.

A native adapter is **not prepared or approved by this file**. A future adapter
must first establish an independently calibrated read-only pilot/order check,
stable direct zone parent and sector/cluster frame conditions, a suitably
observed test volume, appropriate time/protected-file/process fences and
numeric MD velocity syntax. The existing fixture's suppressed null pilot check
alone is inconclusive; an empty current order may omit other AI or default
orders. The earlier `authority-velocity-01` log contains MD conversion errors,
so its recorded movement does not validate the setter. A native test must also
reject these errors and evaluate engine logs before and after operations.

The bounded model tests run via:

```
python3 -m unittest discover -s tests -p test_authority_motion_calibration_offline.py -v
```

They are fake-engine tests. They do not establish a useful time conversion,
axis convention, physics behavior, collision clearance, AI preservation,
smoothness, multiplayer, Windows or Internet support. No MD schema check is
applicable because no MD file has been introduced.
