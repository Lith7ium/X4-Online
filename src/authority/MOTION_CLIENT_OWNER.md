# Experimental read-only client motion IPC owner

`lua/motion_client_owner.lua` attaches the existing local replica MD/FFI
binding to a separately owned loopback UDP socket. The opt-in
`tools/dev/authority_participant_motion_install.py` stages it in a disposable
profile alongside the existing participant/job owner and uses the same X4
`onUpdate`. No actor, sector or zone handle leaves X4. The buffer does not synchronize the source game clock to client real time or
interpolate. The owner does not set pose or velocity, remove a ship, establish cross-process frame identity, or supply
full gameplay. The default replica route still requires the existing
MultiCreate receipt table and job registry.

An optional `saved_baseline` configuration on `new_x4` supplies an enabled
saved-baseline binder, caller-asserted baseline bound and guard. Indices within
that bound use its separate read-only MD event screen; higher indices continue
through the existing MultiCreate-receipt route. Each response is accepted only
on its selected route, and the baseline and ordinary guards are checked around
work. The baseline guard is an external assertion, not proof of checkpoint,
loaded-save or cross-process identity. The shared installer/session and
client sector-interest selection do not yet activate or drive this route.
`tests/test_authority_motion_client_ipc.py` covers routing using the actual
local binders with a fake X4 ABI and simulated MD events; native baseline
motion binding has not been established.

The owner sends one `R|lease|attempt|READY|epoch|generation`; the supervisor
must pin that socket to the intended X4 PID and process incarnation before
using it. One command at a time is accepted:

```
M|lease|attempt|BIND|request_id|epoch|generation|index|sequence|sector_macro|digest|source_time|x|y|z|vx|vy|vz
R|lease|attempt|BOUND|request_id|epoch|generation|index|sequence|sector_macro|digest
```

The 32-hex request ID and 64-hex digest are opaque correlation fields. The
caller is responsible for hashing the exact validated snapshot; Lua echoes the
digest and does not independently authenticate it or the UDP sender. Unknown
velocity is represented only by `-|-|-`; partial and invalid vectors fail. A
separate fresh full 128-bit owner nonce, registry index and per-track counter
form local MD request IDs. The supervisor must generate a new cryptographically
random nonce and fence old events across every owner/process/load incarnation;
the Lua module cannot prove freshness across separate processes. X4
returns `BOUND` only after the correlated replica MD response and the local
FFI binding return successfully, the complete position and optional velocity
sample is accepted by the 3D `hold_only` motion buffer, the owner and clock
guards pass, and no other UDP command is queued. The buffer may discard a rate
at a discontinuity even when push succeeds. The optional `BUFFERED` log is
written after push but before `BOUND`; it is provisional until `event()` and
the corresponding TCP receipt complete. Binding completion before `event()`
returns is provisional. Each subsequent sample needs another local check. Stale sequence,
foreign frame, failed actor/zone/dock/liveness checks, overlapping commands,
late response, missing/ambiguous callback or timeout permanently fault the
owner; no automatic retry occurs.

Only one motion request may be outstanding; the combined owner fences a job
starting while a motion request is pending. The supervisor must serialize the
existing admitted TCP/job/motion owners and maintain process/socket/reader
exclusivity, including duplicated raw descriptors. UDP tokens are not
same-user process authentication. Separate sender, receiver, MD and FFI checks
are not atomic. The local arrival timestamp does not prove remote sample age.
On process loss or uncertain delivery all related clients/owners must be fenced.
Despawn is not implemented here; an upstream despawn must fail closed rather
than generate a false local deletion receipt. Sector transitions also fence
this track instead of assuming cross-process frame continuity.

`tests/test_authority_motion_client_ipc.py` runs real local UDP and the actual
Lua owner/binding with a fake X4 ABI and simulated MD replies. The installer and
shared update-order tests are also offline. The coupled TCP/UDP/Lua test uses real sockets and the real Lua binding and
buffer, with simulated MD and a fake X4 ABI. These tests do not establish X4
runtime operation, smooth movement, Windows, Internet or gameplay.
