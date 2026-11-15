# Experimental supplied-connection load client

`ExperimentalRemoteLoadClient` joins existing experimental codecs, download
and cooperative load-report components for one attempt. It is disabled unless
explicitly enabled and requires an already-connected IPv4 TCP socket, a
separately supplied file-service host, port, token and slot, and a monotonic
deadline. It opens no listener and defines no peer-authentication, encryption,
address-discovery or internet-exposure policy.

The exclusive owner calls `request_offer`, `download`, and `verify_staged` in
order. The download goes into a new caller-owned directory; the caller places
an exact copy in an exclusively controlled X4 save slot and passes that path to
`verify_staged`. The offer controls the expected size and SHA-256. The caller
then reports the actual local load request, marker following X4's load event,
and pause in order with the same attempt ID. `claim` rechecks the staged file,
sends the cooperative assertion and requires an accepted response for that
attempt. After `take_connection`, the caller owns the same stream; response
reading consumes no subsequent command. Invalid, stale or out-of-order actions
by the owning thread after successful construction fault the attempt and close
its stream. Rejected construction leaves the socket with the caller, and a
call from a different thread is rejected without mutating the attempt. There is
no automatic reoffer or retry.

The caller must verify that events refer to its same live game process and
must exclusively control both directories, the staged file, and the connection
throughout. Checks are point-in-time: a successful claim does not prove X4 read
the staged bytes, stayed paused, or that the peer is authentic. A timeout or
failure after a claim was sent leaves host admission indeterminate; fence or
settle the host-side session rather than assuming the claim was rejected.
The existing download uses an inactivity timeout; a slow continuously active
transfer can exceed the absolute deadline. The client rechecks the deadline
after that call, but cannot preempt its filesystem or networking operations.
File-service requests use its existing shared-token HMAC and are not bound to
the TCP control socket. Secrets must be passed by an appropriate private caller.

Tests use real loopback TCP and the existing file service with synthetic local
events. This component has not been connected to X4, Windows, a real remote
peer, or internet transport. The existing participant-control adapter remains
loopback-only, and normal profile setup, compatibility collection, server
listener, remote endpoint/token delivery and native client lifecycle are not
provided. This is not a playable multiplayer client.
