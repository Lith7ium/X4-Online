# Existing NPC constant-velocity diagnostic

This opt-in experiment is not a multiplayer component. It uses a fresh private
copy of the pinned two-sector checkpoint and the existing isolated Linux load,
marker, registry, profile and owned-process supervisor. It targets saved
registry fixture slot 2: an existing ship that must have an operational pilot
and a running `started` or `critical` order before the experiment. Its local
actor and sector handles are independently compared to the prior paused read.
The MD guard requires the same registry mappings, pilot, sector and direct zone
parent, excludes player context and docking/storage, and runs at each request.
Those checks are sampled and the MD and FFI reads are not atomic.

After pausing and observing the load marker, the disposable instance resumes.
It observes three positions one game second apart before any setter, issues a
single zero-vector `set_object_velocity constantvel="true"`, observes three
more positions, then issues a separate `constantvel="false"` setter **without
linear or angular children**, observes three further positions, and requests a
final pause. Each request is correlated and bounded. The result records the
pilot check, order type/state and positions for all phases. Order changes after
the intervention are recorded rather than hidden. A loss of the pilot, actor,
sector or guard ends the run; on failure the isolated process is terminated.
The process is never asked to save or admit a client. Output and source
experiment directories must be disjoint.

The MD schema says omitted velocity children leave those velocity components
unchanged. Whether the standalone release changes constant-velocity behavior on
this active NPC must be observed; an event receipt reports that the cue reached
the action, not its physical outcome. The experiment does not measure native
linear/angular velocity, observe all controls or establish collision clearance.
An unchanged order *type* is not proof of the same order instance, queue,
parameters, mission or job state. No getter for the initial constant-velocity
mode is established, so the release does not establish exact restoration. Even
a completed case cannot establish absence of state loss, universal NPC control,
smoothness, client authority, Windows/internet operation, or gameplay.

Only focused synthetic tests have run. They do not exercise X4 MD semantics:

```sh
python3 -m unittest tests.test_authority_npc_constantvel
```
