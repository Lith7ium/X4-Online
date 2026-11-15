# Experimental sector read preflight component

This is a default-off, **unwired** component for a future, single-X4,
disposable-profile read diagnostic. Importing the Lua file with
`authority_sector_read` other than `true` registers no handlers. There is no
runner, no supported command to launch this probe, and no X4 result for it yet.
It must not be attached to a normal profile or to a multiplayer session.

A future harness could select slot 1 or 2 from the existing saved sector fixture.
`authority_sector_read_guard.xml` checks that fixture and registry epochs match,
that the forward and reverse ship references agree, that the local ship and
sector still match and that the ship is operational and not occupied, docked or
stored. Its writes are confined to cue-local temporary variables; it does not
set jobs, move or create a ship, or create an order. It emits local component
references, pilot presence, and order ID/state as separate MD events.

`authority_sector_read_probe.lua` first asks the existing fixture to verify both
slots, then requests the chosen slot twice, serially. It rejects unexpected or
late events, unsafe original numeric local IDs (including Lua numbers >= 2^53), a lost
pause, a changed actor, sector, pilot/order or position, invalid values and an
invalid or expired local clock. An accepted original handle is a safe integral
number or uint64 cdata, and the converted ID must equal that original exactly;
other, not yet established MD handle types fail closed. It samples the FFI position and game clock only
while its profile and pause guards pass. A completed log row omits runtime actor
IDs. Individual events are not request-correlated: a duplicated first event
sequence could appear to be a second response, so this does not prove two
independent MD reads. It relies on an exclusive in-flight probe and is not a
production protocol. Observations are point-in-time checks, not proof that the
game remained paused continuously.

Synthetic tests use fake MD callbacks and X4 bindings. They do not validate MD
expression semantics, event transport/order in X4, FFI position availability or
the correctness of a returned low-attention coordinate frame. In particular,
the `pilot` and order state expressions and returning a component for an existing
saved NPC require a native observation. Suppressed expression errors can look
like absent pilot or order; such output is inconclusive. An independent binding
between the runtime actor and the saved XML actor is also unproved. No NPC
flight is established here.

## Runner and origin gap

The historical `.local/authority-sector-reference-01` checkpoint has a separate
confirmed pointer and its saved marker and two saved ship/sector relationships
were checked offline. That run's `result.json` remains `success=false` because
its original XML index parser rejected an observed `largefloat`; the subsequent
offline evaluation is documented in `docs/AUTHORITY-INVESTIGATION.md`. Its
original server's three saved-state MD files currently hash identically to their
checkout copies. These facts do not prove which bytes a future X4 load consumes,
that loaded runtime objects match the XML, or multiplayer capability.

The existing `authority_load_live.verify_origin` correctly requires a successful
supported source result and therefore rejects this historical artifact. Weakening
that general gate would be unsafe. The existing download/load harness instead
owns a synthetic coordinator and file service, and its update callback owns the
load barrier. Simply attaching another update callback, trusting an unverified
local receipt, or skipping the origin check would not establish safe sequencing.
A future separate runner needs all of the following before a native experiment:

* Independently check the confirmed and current checkpoint, its digest, saved
  marker and two fixture/registry references, and the relevant source MD files
  and extension profile; retain the historical result and its limitation.
* Copy the verified bytes to a fresh disposable profile, bind the copy and probe
  files read-only, and fence owned process/Steam identity and cleanup from setup
  through final log validation. Do not alter the original profile or checkpoint.
* Within the existing single update owner, wait for load and pause, compare the
  observed loaded marker to the expected marker **before** any read, serialize
  fixture verification and both reads, and fail closed if pause is lost. Avoid
  resume, save, a jobs setter, order creation, admission or a file service.
* Verify the expected marker/read receipts and reject duplicates or later faults
  after owned-process cleanup. Report the precise point-in-time evidence and
  limitations, without treating the marker as proof of exact loaded bytes.

`python -m unittest discover -s tests -p test_authority_sector_read_probe.py -v`
checks the XML structure and Lua callbacks without starting X4.
