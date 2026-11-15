# Ship event research: local X4 9.00 evidence

This is an inventory for experiments, not evidence of universal ship discovery,
event delivery, object creation time, or an implemented replication policy.
The schema is `preparation/game-schemas/libraries/common.xsd` in the project
workspace. Examples below were read directly from the locally installed X4
Foundation CAT/DAT archives; the named paths and line numbers refer to files
inside those archives.

| Event | Schema location and documented payload | Evidence and scope |
| --- | --- | --- |
| `event_job_ship_activated` | 17291–17298: `event.param` is the job ship. | A job ship activated in the galaxy, either spawned in space or completed at a shipyard. Installed `08.cat`, `md/encounters.xml:35–42` checks `event.param.isoperational`. Activation alone does not prove a new ship. |
| `event_god_created_ship` | 14815–14832: `event.object` is the containing space; `event.param` is the ship; optional `space` and `group` filters. | GoD-created ships only. The schema alone does not establish that an unfiltered listener observes every relevant ship or that non-GoD creation triggers it. |
| `event_god_created_object` | 14834 onward: `event.object` is the containing space; `event.param` is the created object; optional `space` and `group` filters. | Generic GoD objects require a ship-class check. Installed `08.cat`, `md/rml_locate_object.xml:98–103` listens with `space="player.entity.sector"`, not as proof of universe-wide coverage. |
| `event_object_built_ship` | 12428–12439: `event.object` is the building object; `event.param` is the operational ship; `event.param2` is the build task. Optional `ship`/`build` filters. | Uses `objecteventsource`; the schema says an `object` is required unless a `group` is supplied (7155–7165). Installed `extensions/ego_dlc_terran/ext_03.cat`, `md/story_yaki.xml:18440–18446` uses `group="$XenonShipyards"` and reads `event.param`. |
| `event_player_built_ship` | 15177–15186: `event.param` is the player-owned operational ship; `event.param2` is the build task. | Applies to player-owned construction, not all NPC construction. Installed `08.cat`, `md/notifications.xml:3701–3708` uses the event and ship parameter. |

The schema describes a group event source as dynamically mutable (1027–1035).
It also warns that changing a variable or property used as a single event
object does not automatically re-enable its listener (1037–1048). It does not
establish a complete, continuously maintained group of all shipyards. A
missing or invalid event object, vanished ship reference, full queue or uncertain
callback ordering must be handled explicitly by any test.

**Hypotheses requiring native evidence:** a shipyard-completed job ship may
appear in both the job activation and built-ship event streams; a GoD-created
ship may appear in both the ship-specific and generic GoD streams. Their
relative order, actual overlap, delivery and lifetime are not established by
these declarations. An experiment combining them should serialize registry
operations, deduplicate by a validated live object-to-registry binding and
retain event provenance; a local registry acknowledgment is neither durable
delivery to a client nor proof of a birth. Other creation paths, including
script-driven creation, remain unaccounted for until independently tested.
