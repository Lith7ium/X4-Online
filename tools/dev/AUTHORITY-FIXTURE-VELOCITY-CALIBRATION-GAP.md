# Fixture velocity experiment: missing runtime calibration

No X4 velocity writer or new executable fixture calibration is supplied here.
The intended target is the saved Company ship at fixture slot 2 / registry
index 4 in an isolated private copy. Until the conditions below are established,
the velocity experiment must not dispatch a setter. In particular, no synthetic
boolean callback is evidence that the target has no pilot, no active or queued
orders, a safe volume, or an aligned frame.

## What already runs

`authority_player_seat_live.py` is an existing opt-in private X4 calibration
runner. It uses its pinned two-sector archive, creates two temporary fixture
ships in a disposable world, and does not save. It can be invoked with the game
path, a new output path and a separately owned private display:

```sh
python3 tools/dev/authority_player_seat_live.py \
  --game '<installed X4 directory>' --out '<new private output>' --display '<private X11 display>'
```

The runner is not a reader for the latest saved fixture checkpoint: it is tied
to `authority_sector_archive_provenance.DEFAULT_STORE`, creates its own test
ships, and its serialized seat procedure requires the NPC positive control and
fixture slots 1 and 2 in order. Its `authority_player_seat_calibration.xml` cue
rejects ships in the local player context. In a saved world where slot 1 is
already controlled, it cannot simply be pointed at slot 2. The latest native
positive-control attempt recorded `assignedpilot=present` with the separate
reservation getter reporting `empty`, and stopped before either target was
classified. The `authority_positive_seat_live.py` search also ended with an
inconclusive outcome. These are recorded observations, not reusable proof that
the intended target is free.

`authority_saved_registry_verify_live.py` is a separate read-only recovery
runner for a saved registered fixture; its source verifier currently expects
the earlier registry-save result schema. The later, successfully recovered
fixture checkpoint uses `authority_saved_registry_checkpoint_source.verify_recovered`.
The saved-registry verifier establishes a specific local mapping, not pilot or
order absence. Neither runner starts X4 merely on import.

## Precise missing evidence

* `@$ship.pilot == null` in the original fixture creation cue suppresses MD
  lookup errors. It cannot independently distinguish a genuinely absent pilot
  from a failed or unsupported getter. `GetComponentData(ship,'assignedpilot')`
  can return nil and describes assignment, not physical or effective control.
* The control-post reservation and assignment getters describe different
  states: the known NPC positive control produced present/empty. There is no
  demonstrated independent negative control proving that either result means
  this target is unpiloted; nor has absence of its complete active, default and
  queued AI orders been established. An empty current order alone is not that
  evidence.
* The LAN velocity path's zone/sector/cluster alignment guard was exercised in
  another native experiment, but it has not measured the target ship's current
  parent hierarchy or rotation. A matching sector macro or a saved offset does
  not establish a matching vector frame. Collision clearance is likewise not
  established by the saved fixture or a `safepos` request.

A meaningful next **read-only** runtime experiment needs a small new owner and
correlated cue for the recovered fixture, rather than pretending the old
seat runner is plug-compatible. It must inspect registry slot 2's saved NPC as
an independently observed piloted control and fixture index 4 as the target,
without creating or moving either. It must log the available unsuppressed MD
pilot/control-post/order observations, UI `assignedpilot`, local ship/sector/
parent liveness and the same numerical relative-basis checks used by LAN.
Unknown getter results, exceptions, timeouts, absent control posts, error logs,
changed actor/parent, or a mismatched positive control remain inconclusive.
The observation can identify which getters actually respond and how they
relate; even a complete response does not by itself prove no AI orders or a
safe intervention.

That owner must run under the existing recovery update dispatcher and private
profile/process/marker fences, retain exactly the seven saved MD script bytes,
and use the recovered-checkpoint provenance verifier. It must not call any
position/velocity setter, pause-independent mutation, save or seat-transfer
operation. It must retain no cross-process component handles. Developing and
reviewing that integration, and collecting a native observation, is still
required; the old runner and synthetic tests are not a substitute.
