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
simulated MD/FFI behavior. This does not establish an actual X4 participant,
server source, complete-universe reconciliation, Windows, Internet, gameplay,
trade, combat or persistent multiplayer. The UI installer and session have not
been executed in X4.
