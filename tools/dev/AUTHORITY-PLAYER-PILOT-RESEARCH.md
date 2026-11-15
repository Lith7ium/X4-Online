# Pilot assignment and seat research

These are local X4 9.00 script-property and vanilla-usage observations, not a
native test of the new fixture ships. The property definitions below were read
directly from the installed game's `08.cat` / `08.dat`,
`libraries/scriptproperties.xml`:

| Property | Documented meaning |
| --- | --- |
| `controllable.pilot` | Pilot entity (line 302). |
| `controllable.assignedpilot` | Assigned pilot, who may not currently be piloting (303). |
| `controllable.controlentity.default` | Main control entity (312). |
| `controllable.controlpostslot.{controlpost.aipilot}` | Slot the control entity inhabits when controlling the object (323). |
| `controllable.slotactor.{slot}` | Actor reserved for the NPC slot or related chair slots (319). |
| `controllable.controlposts.free` | List of free control posts (359). |
| `npc.currentchair` | Chair currently inhabited; not set while the NPC is moving towards it (1432). |

Two potential complementary observations have vanilla usage examples:

1. The UI reads `GetComponentData(ship, "assignedpilot")` when determining
   whether a target has an assigned pilot. See installed `08.cat`,
   `ui/addons/ego_interactmenu/menu_interactmenu.lua:6624–6633`. This checks
   assignment, not whether the character is physically in the chair. Vanilla
   `md/upkeep_management.xml:312` also explicitly makes this distinction.
2. MD can inspect `ship.controlpostslot.{controlpost.aipilot}` and then
   `slot.component.slotactor.{slot}`. Installed `08.cat`,
   `md/npc_state_machines.xml:2342–2346,2407,2820–2835` uses these forms for
   the AI pilot post and slot reservation. A valid slot and its component must
   be established separately before interpreting the actor lookup.

These checks need calibration on an independently known piloted NPC ship and
the intended unpiloted fixture, with live component validity and the relevant
attention state recorded. A missing slot, unsupported getter, suppressed MD
error or ambiguous result is inconclusive. Assignment, reservation, current
chair occupation and a player's ability to take the seat are distinct facts;
the two paths may also rely on the same engine state. Neither a null pilot
expression nor their agreement proves a physically usable seat. In particular,
`people.count` counts NPC templates rather than actual NPCs (property line 374)
and must not be treated as a seat-occupancy test.

Existing isolated sector-read evidence reported a pilot as present for one
existing NPC using `pilot.exists`. It did not validate these additional getters
or the newly proposed player-sector fixtures. A controlled native experiment
would still be required; no new X4 run was performed for this research.
