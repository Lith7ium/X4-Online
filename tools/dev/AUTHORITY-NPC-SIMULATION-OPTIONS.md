# Client NPC simulation: options and evidence

Internal decision note, 2026-11-15. No option is selected here. The objective
is to prevent autonomous client worlds from producing conflicting NPC ships
while preserving the intended server simulation and delegated high-attention
behavior. These are research options, not a working replication design.

## Candidate controls

1. **Limit game systems by space.** The installed X4 schema documents
   `set_space_god_allowed`, `set_space_faction_logic_allowed`, and
   `set_space_jobs_allowed`, with explicit child-space permissions overriding
   parent permissions. The jobs permission is described as primarily affecting
   ship *operating space*; it does not promise to prevent all ship creation.
   Each has a corresponding reset action; the actual jobs action is named
   `reset_space_jobs_allowed` despite the singular name in the setter's schema
   description. The installed base game's `08.cat` / `md/setup.xml` uses
   faction-logic `allow="false"` for several sectors and later reenables it in
   some; `ego_dlc_mini_01/ext_03.cat` / `md/setup_dlc_mini_01.xml` and
   `ego_dlc_timelines/ext_03.cat` / `md/setup_dlc_timelines.xml` enable jobs in
   selected spaces. The documented boolean `jobs` false case, its effects on
   existing or incoming ships, and coverage of non-job creation remain unproven.
   A small MD experiment is plausible; establishing safe, sufficient coverage
   and its effects on economy, combat and high attention is the larger task.

2. **Change individual ships' AI state.** The schema says `abort_scripts`
   aborts an entity's running AI scripts, `cancel_all_orders` cancels an
   object's queued orders, and `release_job_ship` releases a ship from its job.
   None is documented as a durable, reversible general-purpose simulation
   switch. These actions can remove behavior needed for combat, trade, and
   delegated high attention. `set_object_active` is documented as object
   activation with an animation option, not as a proven AI suppression control.
   Restoration and interference with later orders require separate proof.

3. **Reconcile objects through the server register.** The experimental
   [registry](AUTHORITY-SHIP-REGISTRY.md) associates server-issued indices with
   saved MD references. A bounded Linux/Linux checkpoint experiment enrolled
   10,054 observed candidates; it does not establish complete coverage or an
   independent binding of every client runtime object to its saved component.
   Runtime IDs are local, not portable network identities. After a common
   checkpoint, autonomous creation on separate instances has no demonstrated
   shared identity: matching macro, owner, position, seed or similar attributes
   cannot alone prove that two ships are the same object. A causal identity
   mechanism and complete lifecycle handling remain open problems. The
   [create receiver](AUTHORITY-SHIP-CREATE-RECEIVER.md) currently accepts only
   the next index and the player's local sector, does not adopt autonomous
   objects, and does not prevent duplicates or reproduce complete ship state.
   The bounded fixture is not proof of general reconciliation.

These approaches could be combined, but that is an unresolved architectural
choice. Scope, identity and effects must be established before choosing it.

## Discovery is not complete lifecycle coverage

The schema's `event_job_ship_activated` reports activation, including ships
spawned in space or finished at a shipyard; activation alone does not prove a
new object. `event_god_created_ship` and `event_object_built_ship` cover other
described events. Their combined completeness, ordering, and behavior across
all creation paths are not established. The experimental
[job queue](AUTHORITY-JOB-SHIP-EVENTS.md) acknowledges local registration, not
durable delivery or client creation.

Primary schema reference: the locally extracted installed-game
`preparation/game-schemas/libraries/common.xsd`, elements named above. Vanilla
examples are internal catalog paths, not files to copy or redistribute. The
schema describes intended interfaces; it does not establish the proposed
client/server behavior.

## Evidence for a bounded comparison

For a bounded experiment, use disposable profiles and controlled matching
baseline worlds. Compare an unmodified control with each candidate permission
change, one at a time, in selected sectors and explicit child spaces. Record
the effective setup, events, and before/after inventories; distinguish existing
ships, ships entering from outside, job activation, God creation and shipyard
construction. Measure behavior as well as counts: orders, movement, combat,
trade, and local high-attention response. Include creation by a controlled MD
fixture to expose gaps in engine-system controls. A count match alone does not
establish object identity or absence of transient duplicates.

Record whether permissions survive a save/reload and whether child overrides or
restoration change the result. Keep test-only client policy out of authoritative
checkpoints unless that behavior is separately understood. Unknown event
coverage, missing observations, an empty event sample, ambiguous identity or
unconfirmed state is inconclusive. A local Linux result would not establish
Windows, internet sessions, or complete universe coverage.
