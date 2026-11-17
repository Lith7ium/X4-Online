# Experimental client-authority motion reader

`lua/client_authority_motion_reader.lua` is a default-off, read-only local
building block for test client authority over saved registry index 1318 in
`cluster_115_sector001_macro`. It uses the existing saved-baseline bootstrap
and source motion sampler without a job receipt or any X4 write. The caller
must supply a still-valid explicit test grant and a context/checkpoint guard;
these callbacks assert the surrounding session context, they do not prove it.

The X4 session must own the only update hook and route matching descriptor
responses to `event()`, using `expected_request()`. The `stage_sample`
callback is provisional: the owner must keep its actor-free snapshot local and
must not publish it unless `event()` subsequently returns true. Grant loss,
context failure, overlapping/reentrant work, changed actor, sector or
correlation faults the reader. The first velocity is unknown; later velocity,
when available, is inferred from two positions per client game second. The
sample and its times are non-atomic and carry no common-frame assertion.

The optional `include_orientation` setting forwards the sampler's version 2
orientation and angular rate through the same reader and local IPC. Both the
private installer configuration and the Python binding must opt in together;
the default remains version 1. As with LAN NAV2, rates are inferred from
consecutive samples, and the first rate is unknown. This is still restricted
to the fixture above and does not establish player identity, a cross-client
coordinate frame, an X4 setter, or a sector handover. The test connecting the
Lua sampler, UDP, participant and TCP owner simulates X4; it is not a native
multiplayer test.

For the existing isolated two-instance diagnostic,
`authority_client_authority_pair_live.py --include-orientation` sets the
same opt-in on the private installer and Python binding. Two-sample diagnostics
also check the angular rate against the wrapped orientation difference. The
flag does not start a game by itself and is not a general multiplayer option.

The server-side `ExperimentalTCPClientAuthorityMotion` can also be created
with an explicit `connection_handle`. Up to two such owners may share the
existing serialized TCP reader, each with its own grant, incarnation, request
and sample sequence. The selected handle must still be admitted with the
grant's incarnation at every pull. Activity or disconnection on the other
admitted socket during a pull fences the operation. Without a handle, the
original one-admitted-participant restriction and exclusive ownership remain.
These are caller-supplied test grants; the two-peer tests simulate participants
and do not establish real multiplayer authority or X4 control.

The private fixture diagnostic can instead select player slot 1 or 2, bound to
saved registry indices 3 and 4. It verifies the locally controlled ship around
each read and exchanges a PID-checked READY/ARM before binding the same UDP
peer. An idle source may survive a pause; a pending request or datagram during
pause fences it. The optional two-client observer reads 6D samples and rates,
but does not write them to server X4. Its delivery owner is retained until the
diagnostic server ends. This fixture path does not establish a common frame,
movement replication, sector transitions or playable multiplayer. Tests using
the TCP worker and Lua state machines simulate game components and MD.

An isolated Linux run on 2026-11-17 loaded the server and seated two real X4
clients in the fixture, but its player-source observation exceeded the
40-minute orchestration deadline. Cleanup was confirmed. The run did not
record per-pull progress, so it cannot establish whether samples or rates
arrived; it is a failed diagnostic, not a successful native movement test.
The process repeatedly hashed the same saves, accounting for more than
500 GB of logical reads, largely served from the cache. Separately, the
pull-driven sampler requires adjacent source measurements within one game
second to derive velocity; the failed run did not prove which limitation
caused its timeout. See `FIXTURE_PLAYER_LATEST_CACHE.md` for the unintegrated
continuous-sampling experiment.

This module installs no hooks, socket, transport, scheduler or server writer.
An opt-in participant-session adapter is described below; it has not been
validated in native X4 and does not implement client departure/handover. The user-approved policy is that another present
client takes over, or the server does when none remains; the mechanics and
correct transfer remain unimplemented. The accompanying tests use actual Lua
bootstrap and sampler state machines but simulated MD/FFI, not X4.

The separate opt-in `client_authority_motion_session.lua` reuses the local
Source Motion IPC protocol. After the PID-bound peer handshake, a
`REGISTER_SAVED` for index 1318 is acknowledged only once the reader's real
bootstrap event has returned and its sampler has registered. Each `PULL`
drives at most one local read; `NO_SAMPLE` does not advance the sample
sequence. The session publishes a staged snapshot to IPC only after a
successful reader `event()` return and a new guard check. It registers no
onUpdate hook; the participant session supplies the single guarded descriptor
router and update tick.

The private installer `tools/dev/authority_participant_client_authority_install.py`
adds this mode explicitly and does not create a grant. Its configuration calls
an independently injected `X4LAN_CLIENT_AUTHORITY_TEST_GRANT` with epoch,
generation, index, test token, participant incarnation and world session epoch. The outer supervisor
must bind that grant and the local UDP peer to the actual client process. A
successful callback is a test assertion rather than an implemented transfer or
HA lease. The Lua installer/IPC tests simulate the game and do not prove the
network, actual X4 lifecycle, client departure or server-side application.
