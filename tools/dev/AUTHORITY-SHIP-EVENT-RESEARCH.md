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

## Additional local evidence and a bounded observer design

The installed base and DLC catalogs were scanned read-only for these event
names in `md/*.xml`: 44 CAT/DAT pairs and 386 catalog entries, including
multiple versions where present. Catalog MD5 matched each entry cited below.
This is a scan of those archived MD entries, not a runtime coverage census or
proof about uninspected content or enabled DLC. Schema references below are to
the locally extracted `preparation/game-schemas/libraries/common.xsd`.

| Event | Documented parameters | Concrete local usage and remaining uncertainty |
| --- | --- | --- |
| `event_god_created_ship` | `event.object`: containing space; `event.param`: ship. Optional `space` and `group` attributes; no `objecteventsource` requirement in this declaration (14815–14832). | No use found in the scanned MD entries. Unfiltered subscription semantics, overlap with other events and whether it sees ships from other creation mechanisms remain untested. |
| `event_player_built_ship` | `event.param`: player-owned ship; `event.param2`: build task. No filter attributes in this declaration (15177–15186). | `08.cat/md/notifications.xml:531–537` treats this as an existing, non-operational player-owned object becoming operational; lines 3701–3708 use the task's building object and ship. This does not establish an object-creation instant, NPC-build coverage, or safe repeated notification behavior. |
| `event_object_built_ship` | `event.object`: builder; `event.param`: operational ship; `event.param2`: build task (12428–12439). An `object` or existing, dynamically mutable `group` is required by `objecteventsource` (7155–7165, 1027–1035). | `ego_dlc_terran/ext_03.cat/md/story_yaki.xml:18430–18445` finds a bounded Xenon shipyard group and listens to it. Completeness and maintenance of a universe-wide shipyard group are not established. |
| `event_object_entered` | `event.object`: entered space/container; `event.param`: entering object; `event.param2` and `event.param3`: new and old contexts (14879–14897). | `08.cat/md/notifications.xml:542–548` uses `space="player.galaxy"` as one cause of a player-owned operational object's arrival/spawn. `md/rml_locate_object.xml:98–110` uses a sector-scoped listener. The schema says an object can enter *or* be created: **do not classify entry as birth**. Universe-wide event coverage, context-change behavior and event volume remain untested. |
| `event_job_ship_activated` | `event.param`: job ship; documented for activation after direct space spawn or shipyard completion (17291–17298). | `08.cat/md/encounters.xml:35–42` filters for operational encounter ships. Activation does not establish a new registry or client object, nor cover non-job ship creation. |

In this scan the event-name counts were respectively 0 GoD ship, 2 player
built ship, 1 object built ship, 7 job activations, and 1 GoD-created object.
Those counts include archived variants and are not counts of active cues.
The `event_object_entered` example was inspected separately; no exhaustive
count of that more general event is claimed. Script-created ships, ships
created before subscription, other build/ownership paths, listeners' possible
overlap, and events missed during loading or queue overflow remain open.

A useful next implementation would be an independently enabled, disposable
observer with one serialized owner. It can record the event kind, ordered local
sequence and a locally valid ship reference; any exposed transport must use an
opaque event identity, never an X4 actor handle. At observation time it can
read the existing registry's epoch and bidirectional `byship`/`ships` entries
without modifying them: absent entry, consistent existing entry, and invalid or
inconsistent entry must remain distinct outcomes. A missing entry is **not**
proof of a birth. `Enroll` is unsuitable for a read-only observation because
it allocates a new index for an absent ship, changing the later job owner's
classification. The saved census fixture has the same underlying registry
fields but must remain byte-identical to the script serialized in its save.

The observer needs a separately bounded queue, explicit overflow/unavailable
faults, a unique run/queue incarnation, no implicit acknowledgments, and
exclusive serialized ownership if it ever shares registry mutation or source
queue consumption with the job host. Preserve every observed event and its
provenance until examined; deduplication may only follow validated local
identity and cannot silently discard a possible distinct event. A ship may be
unavailable or non-operational when sampled, and `player.galaxy` needs a valid
player context; those conditions must remain failures or explicitly recorded
inconclusive observations, not negative proof of creation. No such observer is
implemented or natively validated here. A future native test needs a separate
agreed plan with a controlled creation path, comparison against independent
evidence, owned process cleanup and explicit expectations for duplicate,
missing, late and overflow events.
