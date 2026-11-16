# Experimental X4 participant job client

`lua/job_client_owner.lua` is a default-off serialized endpoint for a running
local X4 participant. `new_x4` registers one `X4AuthorityMultiCreateReceiver`
event router but does not install `onUpdate`. The private
`tools/dev/authority_participant_job_session.lua` drives participant control and
the job endpoint from the same tick; `authority_participant_job_install.py`
connects that tick to the existing isolated download/load owner after marker and
pause observation. It installs only on explicit invocation and starts no game.
The resulting single update hook, both local UDP endpoints, profile, process,
and event registrations must be exclusively owned and fenced by the supervisor.
The participant can resume through the existing local control protocol. A pause
or other lost running guard after the job owner starts fails it closed; no join,
save, reconnect or pause arbitration is implemented here.

The job endpoint accepts one event at a time from a dedicated connected local
UDP socket. The Python bridge first binds its socket, validates the unique X4
peer after `READY`, and must have a shorter deadline than the surrounding TCP
exchange. Packets carry fresh lease, attempt, request, registry epoch, queue
generation, sequence, index, descriptor digest and descriptor. The digest is
only echoed by Lua, not independently recomputed there. Neither it nor the
local UDP tokens authenticate the process or replace process/socket ownership
checks. Raw local actor and sector handles are never sent in this protocol.
Malformed, duplicate, unexpected, timed-out, uncorrelated or partially applied
operations permanently fault the owner. The caller must fence the case; no
uncertain event is retried. An IPC receive returning no packet cannot distinguish
an oversized discarded datagram from no traffic, so loss eventually times out.

A caller provides an explicit synthetic seed and a sector-to-witness table from
the hash-pinned census evidence; the installer rejects absent or nonmatching
entries. The running MD receiver rechecks that the local witness remains
operational, correctly reverse-mapped and in the uniquely resolved local sector.
The owner arms the running FFI inspector before Create, demands the correlated
MD Inspect, and emits `APPLIED` only on a subsequent tick after successful client
completion. Time samples, actor identity and the local position check do not
prove an atomic source descriptor, a shared cross-process coordinate frame,
complete ship state or continuous game-time advancement. Seed and approximate
loadout are not recovered from the source. Some sectors have no eligible saved
witness and witnesses can move or disappear; no fallback is implemented.

Focused offline tests drive the real Lua client and inspector through a fake C
ABI, and connect the actual Python IPC and Lua owner over local UDP with
simulated MD/FFI behavior.

## Bounded native observation, 2026-11-16

The single isolated Linux X4 run `.local/authority-tcp-job-x4-01` reported
`success: true`, a coordinator-reported TCP job receipt and no remaining owned
processes. The X4 log records the load request, marker and pause observations,
then `RUNNING` at game time 3.037 and `LOCAL_APPLIED` for index 10055 at
3.130753225 in the configured `cluster_01_sector001_macro` test case. The
log does not independently record the individual MD or FFI values. The owner
code emits `LOCAL_APPLIED` only after the separately correlated MD responses
and local FFI inspector accept the operation, and before its UDP `APPLIED`
response. The TCP participant code sends its receipt only after the UDP bridge
returns success. This cross-process ordering is supported by code and the
coordinator result; no packet capture was taken. The worker checks local UDP
peer ownership against the X4 process via `/proc`; this is supported by the
worker code and its success result. The raw PID, socket-inode and receipt values
were not retained as independent evidence.

The diagnostic used a real local TCP host/participant delivery path and local
UDP to the isolated X4 owner. The server engine, its admission claim and
checkpoint, and the submitted ship descriptor were synthetic; the checkpoint
offered by that synthetic coordinator was not supplied to X4. X4 was separately requested to load the staged census checkpoint; the
expected marker and pause were observed. Exact X4 file consumption was not
independently proven. The test descriptor
used macro `ship_gen_m_tugboat_01_a_macro`, faction `pioneers`, artificial
seed 7183, synthetic local coordinates `(-400, 100000, 500)` and an approximate
level-1 loadout. It did not originate from a live server NPC event.

The game-time samples do not prove uninterrupted running. This one local test
does not establish source-to-client integration, multiple X4 clients,
complete-universe reconciliation, a shared cross-process coordinate frame,
Windows, Internet, gameplay, trade, combat or persistent multiplayer. The
result makes no claim that the entire X4 log is free of unrelated errors.

An opt-in multi-witness experiment is prepared for the source-to-TCP pair
runner. Its installer requires the full eligible, pinned census candidate list
for each represented sector; the indices are local saved-registry references,
not process-specific actor handles sent over the network. The existing client
owner copies and checks that list. The client asks MD to inspect candidates
serially with distinct correlated request IDs before issuing one Create. The
existing Create and Inspect checks remain in force; if the selected witness
changes or the Create outcome is uncertain, the operation fails rather than
trying another candidate after mutation may have begun. The operation deadline
includes witness selection and Create/Inspect, so an exhausted candidate list
or timeout is possible. Offline tests cover candidate fallback, exhaustion,
invalid lists, timeout and no retry after Create refusal. No native
multi-witness result or complete-universe coverage is asserted here.

For a specifically opted-in fallback diagnostic, the participant logs only
validated, request-correlated witness responses as target registry index,
sector macro, saved witness index and eligible flag. The runner requires at
least one target with an ineligible earlier candidate and an eligible later
candidate, followed by that target's local apply and the worker's completed
receipt/MD-Ack/REARM record. The marker alone is neither an apply nor a network
acknowledgement. Marker order, candidate membership and the correlated completed
index are checked; no actor handles are emitted. This evidence requirement is
experimental and can make a test inconclusive even if ordinary delivery works.
