# Experimental sector read preflight component

This is a default-off component with a separate opt-in single-X4,
disposable-profile runner. Importing the Lua file with `authority_sector_read`
other than `true` registers no handlers. One isolated Linux X4 run is recorded
below. Do not attach the component to a normal profile or a multiplayer session.

The runner selects slot 1 or 2 from the existing saved sector fixture.
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

Synthetic tests use fake MD callbacks and X4 bindings. They do not establish MD
expression semantics or event transport/order in X4. One native case reported a
pilot, order state and FFI position as described below; this does not establish
the behavior of other ships or the correctness of every low-attention coordinate
frame. Suppressed expression errors can look like absent pilot or order; such
output is inconclusive. An independent binding between the runtime actor and the
saved XML actor is also unproved. No NPC flight is established here.

## One native read

The single disposable Linux run `.local/authority-sector-read-01` recorded
`success=true` for slot 2. Its local log ordered the load request, matching
marker observation, read receipt and then `pause_observed`; the probe checked
pause at individual read points. It reported pilot `present`, order ID `Patrol`,
order state `started`, game time `3.014` and FFI position
`(-90852.75, 6354.83984375, 79232)`. The result reports no remaining owned
processes and no checkpoint request. The engine log also records a failed
attempt to write the read-only `config.xml`; the diagnostic nevertheless
completed its bounded read. This run requested no jobs change or new order.

The result does not demonstrate movement or continuous pause, independently
correlate both MD read responses, prove the loaded bytes or independently bind
the runtime actor to its saved XML component. It is not an A/B jobs test, client
admission, multiplayer or gameplay evidence.

## Runner and origin

The historical `.local/authority-sector-reference-01` checkpoint has a separate
confirmed pointer and its saved marker and two saved ship/sector relationships
were checked offline. That run's `result.json` remains `success=false` because
its original XML index parser rejected an observed `largefloat`; the subsequent
offline evaluation is documented in `docs/AUTHORITY-INVESTIGATION.md`. These
facts do not prove which bytes X4 loads, runtime-to-XML actor identity, or
multiplayer capability.

The standalone `authority_sector_read_live.py` uses the fixed-candidate
`authority_sector_archive_provenance.verify` rather than weakening the general
`authority_load_live.verify_origin` gate. It requires equal CURRENT/CONFIRMED
pointers, stable archive evidence during verification and staging, a copied
checkpoint with the recorded digest, and matching extension lists and existing
saved-state MD files. It creates a fresh private profile, mounts the staged save
and scripts read-only, checks the owned process and Steam identity, and cleans
up owned processes. A pipe-gated helper cannot execute the launcher until its
process start identity is captured and pending termination signals are checked.
Signal handling is best effort: a signal arriving after that check and during
the gate write can still allow a brief launch; the next check fails the run and
attempts owned-process cleanup. An unconfirmed stop or surviving owned process
leaves the lock pathname in place and reports the cleanup failure. Other cleanup
steps continue even if stopping the process raises an exception.
It has no coordinator, file service, save, jobs setter,
order creation, resume or admission. Its random ticket is for local diagnostic
receipts only and has no admission meaning.

The existing load callback remains the sole update owner. It checks pause,
checks the loaded marker against the expected saved marker, and then invokes
the read probe. Its `pause_observed` receipt is emitted **after** the read, not
before it: earlier pause observations come from point-in-time Lua/FFI checks.
Marker receipt does not prove the exact loaded bytes. The runner validates the
ordered marker/read receipts and checks again after process cleanup. It reports
pilot and order as game-reported values: absent/none may reflect suppressed MD
errors; order ID is a type identifier, and a single reported pose is not a
movement observation. The runner scans each stable full log snapshot for its
probe faults and known X4 Lua/MD error patterns; this is not a guarantee that
every possible error format is recognized. It checks log identity and previously
read bytes for changes between snapshots, including after cleanup.

The timeout limits the launched process observation; archive validation occurs
before that timeout. Use of the runner requires an explicit private output path,
local display and slot. The archived source profile and checkpoint are only
read; the output is disposable. The one native result above is restricted to
that slot, checkpoint, process and observation.

`python -m unittest discover -s tests -p 'test_authority_sector_read_*.py' -v`
checks wiring, receipts, interrupted cleanup, XML structure and fake Lua
callbacks. Harmless helper processes are used to test the exec gate; X4 is not
started.
