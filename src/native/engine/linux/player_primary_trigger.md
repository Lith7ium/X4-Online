# Finite Linux primary trigger experiment

This is a default-off, disposable experiment for the exact pinned Linux 9.00
image. It is **not human FIRE replay**, a wire change, aiming, secondary fire,
missile support or accepted deterministic combat. The shared stock-v3 codec
defines a FIRE bit, but the default Linux input policy rejects it. The separate
[human-primary experiment](player_primary_human.md) can explicitly admit it;
this scripted experiment is mutually exclusive with that mode. Both peers
instead execute the same explicit script:
primary trigger true at simulation ticks 70..75 (six generations), false at every
other applied generation in a T40 session. These are simulation frames, not
wall-clock seconds.

Build a new frozen bundle using the existing matched T40 independent physics
and resident worker-dispatch options, adding:

```
--player-primary-trigger-experiment
```

The bundle must have `--worker-dispatch`, `--player-startup-phases v1-t40`, and
matching independent/UI session lengths 180..900. Retain the existing finite
budget, world/body evidence and local stop option. Use the normal `run` command
against that newly built bundle; never retrofit an environment variable onto
an old bundle. The manifest pins `player_primary_trigger_experiment=true`,
source version 19 and the complete helper/source closure. The runner strips an
inherited `X4_DEV_PRIMARY_TRIGGER`; only the frozen opt-in sets `script-v1`.
Root owns native run authorization and acceptance.

`keyboard_probe_prepare_independent_slots` admits the scripted generation after
both records validate. `player_physics_network_begin` applies it after both
independent slot effects return, while the authenticated exact-ticket worker
has joined path work and main remains parked. Both ships and fixed primary
groups are staged and checked before references/controllers change. At most 16
exact Weapon components per slot are retained through the existing native
Component reference API. All guns must initially be idle and have either no
controller or the exact PlayerShootController. Unknown initial controllers,
changed groups, duplicate guns and later controller replacement fail closed.

Construction follows the pinned script's no-target Mindless constructor using
the native aligned allocator. The native installer owns the new controller,
including native release of its previous controller. The adapter invokes the
Mindless setter and posts the stock ShootTargetSetEvent plus the owner's
WeaponShootTargetSetEvent, selecting the script branch without optional
Activate/Deactivate events. Identity/controller checks follow native callbacks;
the staged initial controller is checked again immediately before installation.
The installed trigger is neutralized before returning to native movement.
Subsequent generations only rewrite/read back the owned trigger. The planned
burst ends with setter(false), leaving controller and component references
resident. Failures terminate the disposable process; no rollback or reference
release occurs from an uncertain callback context. Existing finite exit 223 and
resident local stop/terminal exit 225 remain separate outcomes.

The generic Component retain prevents allocation destruction; it does not lock
controller ownership or freeze every UI/event thread. This experiment uses the
engine's existing worker ownership ordering, matching the practical Windows
lease model, and rejects observed drift. It does not establish universal
concurrent-writer exclusion. Retained components can logically detach; fresh
runtime/group/ancestry checks remain mandatory. Every gun check additionally
requires the pinned native operational predicate fields (+0x68==0,+0xd1==1),
including after callbacks and on every generation. Linux+0xd3 lifecycle
semantics are not inferred from the Windows layout. Native notifications can invoke
callbacks. No allocator/installer is retried after a partial result.

Bounded stderr receipts cover every apply generation, worker identity, script
value, fixed gun counts and **actual gun+0x2fd firing counts**, separate from
setter/trigger bytes. They are independently hash-bound to complete accepted
physics before result compaction. Firing is sampled before that generation's
component walk, so shot onset can appear in the following sample. Raw failures
remain retained. Equal trigger/firing receipts alone do not prove equal bullets,
hits, damage, ammo, heat, RNG, HUD reload behavior or combat.

A paired Linux run at source `465b44e` completed 180 physics generations
(ticks 40..219). Each ship had two primary guns. On both peers, both ships'
actual firing counts were two at ticks 71..76 and zero elsewhere, consistent
with sampling before the component walk. The 219 recorded rolling-world rows
and 720 player-body rows matched. This validates the bounded scripted trigger
and its release; it does not establish projectile, hit, damage or full-world
equality. The disposable processes exited with the expected code 223. Human
trigger capture and replay now have a separate default-off implementation, but
the first native capture run stopped at registration admission before input.
That path has no native human-fire acceptance.
