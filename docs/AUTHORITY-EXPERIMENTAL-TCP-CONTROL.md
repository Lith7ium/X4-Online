# Experimental cooperative TCP load control

`authority.experimental_tcp_control.ExperimentalTCPControl` is an explicitly
opted-in, single-owner prototype around `TrustedMarkerLoadSession`. It opens no
listener or thread, and it does not start X4, transfer a save or advance the
world. A caller accepts an IPv4 TCP stream socket, passes that exact live socket
to `adopt`, drives the coordinator's pending pause/save operations on the same
owner thread, and repeatedly invokes `poll`. Direct use of the underlying
session, coordinator or service must also be serialized by that owner.

The wire frames are newline-delimited, with at most 4096 bytes before the
newline. A client sends the `offer_request()` frame after the caller has brought
the coordinator to a confirmed paused baseline. An earlier request receives
`{"version":1,"kind":"not_ready"}` without an offer or session fault; it may
be sent again after the caller finishes the pending coordinator work. The
channel replies with an encoded `MarkerBoundOffer`; the client performs its own transfer/load steps and
sends an encoded `HonestClientLoadClaim`. On a matching current claim, the
channel replies with `{"version":1,"kind":"accepted","attempt_id":"..."}`.
The accepted state means the host trusted that client's assertions; it is not
proof of exact X4 file consumption, continuous pause or correct game state.
A second `offer_request` that actually returns a new offer before acceptance
replaces the attempt; `not_ready` itself is not a new attempt. Stale claims,
wrong connections, malformed/oversized frames, EOF and expired incomplete
requests are refused by closing that socket. Requests must not be pipelined;
the next frame is sent only after receiving the prior response.

During the handshake and pending response the timeout is absolute for the
current complete frame, so sending partial bytes does not extend it. Once an
accepted response has been sent, idle alone does not remove the participant;
the caller must continue polling and handle connection loss. The channel does
not provide heartbeats or automatically restart a session. Socket liveness is
checked immediately before and after accepting a claim, but a peer can close
just after either check. Before dispatching a pending resume the exclusive owner
must call `ready_for_resume()` and defer the resume when it returns false. The
gate requires pending replies to be drained to the local socket, defers unread
input, and disconnects observed EOF. The owner must continue polling when the
gate defers. The coordinator must still validate its own readiness. The gate
does not prove that the remote received the reply or that a peer remains live
after the check; it can be bypassed by an incorrect caller.

An uncertain partial coordinator mutation or cleanup exception faults this
channel and closes its adopted sockets. It does not roll back the world:
other associated service offers and transfers may still exist. The owner must
fence and safely settle or discard the coordinator and file service; replacing
only this object is not recovery. Transport identity means the specific socket
object, not authentication of who is on the other end. There is no encryption,
identity verification, save transfer, content compatibility check, native X4
load or gameplay integration here.

`tests/test_authority_experimental_tcp_control.py` uses real IPv4 TCP sockets
bound to `127.0.0.1`, a fake engine, fake save service and disposable marked
checkpoint. It tests framing, disconnects, stale and wrong-peer claims,
timeouts and partial failures. These tests do not demonstrate Windows, Internet,
real X4 or multiplayer. Loopback is the current test boundary, not a final
product requirement; the prototype does not open or configure a public listener.
