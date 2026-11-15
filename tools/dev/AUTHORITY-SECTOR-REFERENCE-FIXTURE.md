# Disposable two-sector reference fixture

`authority_sector_reference_fixture.xml` is a default-off MD experiment,
installed only in a disposable overlay by the opt-in runner described below.
It stores references in its own saved MD cue; it does not create ships, change
their positions, or set world objects. One bounded native observation is
described below; it is not a general MD schema validation. The accompanying
synthetic tests inspect XML structure and guards; they do not execute MD semantics.

After the caller pauses an isolated disposable world and enrolls two existing
operational ships into the existing ship registry, send `Initialize` to screen
`X4AuthoritySectorReferenceFixture` with `epoch`, `index1`, and `index2`. The
caller must validate the epoch and integer inputs and permit only one request
in flight. This one-shot cue accepts only distinct ship references in distinct
sector objects with valid registry reverse mappings. Its two fixed slots assign
sector indices 1 and 2 to these distinct references. `Initialized(epoch)` means
the fixture stored the snapshot; `Refused` or a missing response ends the test.
Do not retry initialization after uncertainty.

Send `Verify` with the epoch both before the save and after loading that same
marked checkpoint. `Verified(epoch)` requires the original ships, indices and
two sector references to remain present, operational, mutually distinct, and
consistent with both directions of the ship registry, and each ship still to
be in its saved sector. A changed or unavailable ship/sector fails rather than
being reclassified. The caller must check the pause continuously, fence the
checkpoint and process identities, serialize events, and enforce deadlines;
this cue does not itself observe pause, transfer or process state.

The two slots establish only the asserted relationships inside this fixture for
the observed run. They do not prove
independent runtime-to-save identity, sector coverage, movement replication,
parallel players, or multiplayer. The runner selects ships from two observed
distinct sector objects rather than assuming the first two census entries meet
that condition; the MD guard independently requires distinct sector references.

`authority_sector_reference_evidence.py` is a separate, read-only checkpoint
checker for the runner's two-entry registry and fixture. It first validates the
existing registry's saved forward/reverse mappings, then checks both fixture
ship slots and their distinct saved sector component references against each
ship's unique sector ancestor in the checkpoint XML. Its accepted serialization
includes the representation observed in one native checkpoint; it fails closed
on a different or ambiguous representation. The checker proves
only properties of the checked checkpoint bytes, not which objects or bytes a
running client loaded. The existing census wrapper cannot be reused unchanged:
its identity layer deliberately creates two fixture ships, whereas this
experiment requires existing ships.

`authority_sector_reference_live.py` instead composes the existing two-X4
supervisor and marker components directly. It installs a fresh two-ship
registry, marker and this fixture into isolated profiles. Before checkpoint it
selects existing operational candidates, enrolls them serially, verifies the
fixture while paused and checks the server pause before each bridge update.
These sampled checks do not prove uninterrupted pause or zero elapsed game time.
After local checkpoint transfer and the load event, the guest checks
the marker and fixture while paused. The confirmed checkpoint must match the
offered checkpoint ID and hash, contain the marker and pass the separate saved
slot/ancestry checker. No existing normal profile or save is used.

On 15 November 2026, `.local/authority-sector-reference-01` selected two
existing ships in distinct sectors in one isolated Linux X4 process, saved and
transferred the checkpoint, and loaded it in a second isolated Linux process.
Both process logs report the fixture's `VERIFIED` response; the marker was
stored and inspected after load, and the original result reports client pause.
The original `result.json` records `success=false` with `invalid fixture index`:
the first checker accepted only `integer` while X4 serialized the two valid
indices as `largefloat` values `1` and `2`. That historical result is unchanged.
After correcting the parser and adding a regression test, an offline reread of
the same confirmed checkpoint verified both ship registry mappings and the two
saved ship-to-sector ancestor relationships. This later result is separate from
the original failed runner result; no second native run was performed.

The runtime assertion is an MD self-check, not an independent binding of each
live object to a saved component. Matching a staged checkpoint and marker does
not prove the exact bytes X4 consumed. Fleet enumeration and its first large
faction list can exceed the bounded deadline; a timeout does not by itself
indicate an identity failure. No player is admitted, and no gameplay, Internet
operation or universe-wide coverage is established.
