# Experimental census replica client owner

These default-off components are not installed automatically. They start no
X4, register no handlers on import and have no update loop, socket or ACK sender.
A caller must explicitly bind `authority_census_replica_client_x4.lua` to the
existing sole X4 event/update owner in a disposable profile. No normal save or
profile is suitable. The surrounding harness must verify both checkpoint
baselines, process identities, read-only staged save and protected files, retain
one exclusive consumer for `X4AuthorityCensusReplica` events, and fence its
queue, timers, helpers and sockets until final cleanup.

The caller must pass the actual received and validated job-descriptor table from
the local test transport and a fresh successful local sector-witness result.
The owner checks their epoch, attempt, fixed index 10055, sector macro, saved
witness index at most 10054 and descriptor fields. Those caller-supplied values
are assertions, not independent authentication or proof of the exact loaded save.
The seed 7183 is a test creation parameter; it is not a readback of source ship
state. The receiver creates a deliberately approximate ship, not a complete
reconstruction of its loadout, AI, health or trade state.

After a matching paused guard and an operational faction/macro candidate
baseline, the owner issues Initialize, one Create, a correlated MD Inspection,
then checks the local actor/sector using FFI, no-docking getters, finite
coordinates, paused game time and per-axis distance at most two metres. Only
then may it issue the identical replay. A second Inspection must refer to the
same **local** actor and sector and pass the same readbacks; candidate count
must remain baseline + 1. The existing faction-list API and count cover only
observed candidates, not the whole universe or collision safety. Other ships
can have the same faction/macro. The MD inspection advances its test phase
before the external FFI readback; a failed or uncertain first inspection must
fault and discard the case, with no replay or retry. Local actor and sector
handles and comparison keys are never included in the returned intent.

After the second inspection, `event` returns in `intent_pending`. A later
successful `tick` moves to `intent_ready`; `take_intent` checks its injected
`release_guard` and paused/time guards again, then returns only
`attempt, epoch, transport_sequence, job_sequence, index`. This is a local ACK
intent, not an ACK or delivery proof. The harness must independently verify the
source/client process, pause, witness, queue and transport fences after
receiving the intent and before sending any real TCP ACK. `release_guard` is a
caller-provided local observation and cannot by itself prove Python-side
process identity. A guard failure, callback exception, late event, duplicate,
timeout or ambiguous dispatch fails closed; no automatic retry or adoption of
an existing ship occurs. The owner never deletes a ship.

All pause, file, identity, FFI and MD checks are sampled rather than atomic.
A successful fake test or future isolated native run would not prove continuous
pause, exact source/client sector-frame identity, visual smoothness,
collision-free spawning, full NPC simulation, Windows or multiplayer gameplay.

Offline state and fake FFI tests:

```
python3 -m unittest discover -s tests -p test_authority_census_replica_client.py -v
```
