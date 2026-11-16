# Disposable player-seat calibration experiment

This opt-in development harness loads the pinned two-sector checkpoint in one
private Linux X4 process, observes its checkpoint marker and slot-2 NPC, and
pauses it. A single existing load-update owner then checks a fresh fixture
preflight, creates two test ships once, and performs three serial seat queries:
the existing NPC is the positive control; the newly created player-owned ships
are the two negative observations. No Save or save-bridge authorization is sent.
The private save directory is mounted read-only. The source archive and all
executed private scripts remain protected and are checked by the supervisor.

The preflight and creation are separate events, not an atomic transaction. It
requires the `custom_creative` module, the saved healthy two-entry register,
matching distinct sector/ship references and an unused fixture state. An event
refusal, unexpected or duplicate event, partial creation, lost pause or guard,
missing getter response or timeout faults the attempt without a retry. A first
ship may already have been created on a subsequent failure; the process and its
private world are discarded. A receipt counts two returned references, not all
world objects created. The original sector-read guard imposes an additional
30-second interval from its first read, even when the experiment deadline is
longer; an overrun is a fault, not a negative observation.

Completion requires that the NPC's local actor and sector match the earlier
read and that assigned-pilot and slot-reservation getters both report occupied.
Each test ship must report `assignedpilot` as `nil_observed` and its MD slot
reservation as `empty`. Both refer to the fixture's local actor and saved sector
at the time read. Runtime handles are not included in the experiment receipts.
The getters do not prove that their positive results identify the same pilot;
`nil_observed` and `empty` do not prove a physically empty, usable, or
player-controllable seat. The fixture checks `faction.player`, macro, sector and
operational state; `safepos` does not prove collision-free placement. These
observations do not establish multiplayer, shared faction/account state,
byte-exact engine loading, or gameplay. The source artifact and log checks are
point-in-time guards, not an atomic guarantee over the process lifetime.

Only the private experiment may install the additional MD/Lua files. The
fixture-creation handler remains one-shot and disabled in normal installs;
`PlayerFixtureBridge.save()` remains blocked. The experiment should be run
only from a shell after separate review of the current changes and environment;
no native result or Windows/Internet claim follows from the synthetic tests.
