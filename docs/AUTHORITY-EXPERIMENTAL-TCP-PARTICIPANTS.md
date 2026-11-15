# Experimental TCP participant control

`ExperimentalTCPParticipants` is an opt-in synchronous participant adapter for
one `ExperimentalLocalHost`. Construct it before any connection joins, then
install it as the matching world's participant adapter before driving the host.
Only the exclusive host owner may drive the world, service and control sockets.
The owner must call it only from its active `WorldCoordinator.step`; its
busy/pending checks alone do not prove that call context. This adapter does not
invoke `poll`, `disconnect`, `step` or any other coordinator mutation.
Control and participant I/O never concurrently own the same socket. This is a
bounded local experiment, not a commitment to this architecture.

For each ready handle it looks up the existing admitted socket and sends a
bounded newline-delimited JSON `participant_command`, with version, epoch,
connection handle, a strictly increasing request ID and `pause` or `resume`.
The cooperative client is expected to perform the local X4 control operation
and answer on that same socket with a `participant_receipt` matching those
fields and `status: confirmed`. No client-side network implementation exists
here: the tests use synthetic responders, not X4. Request IDs belong to the
adapter lifetime; never replace it in a live world or reuse an epoch to make
old messages appear current.

One absolute deadline covers the whole participant set. Calls block the host
owner: no new joins, load requests or ordinary control frames are processed while
the exchange runs. Participant commands are sequential, so a later failure can
leave earlier clients in a different state. Unknown, duplicate, mismatched or
malformed replies, read/write failure, observed disconnect and timeout fail
the operation permanently without retry. The caller must fence or settle all
affected clients, coordinator, server and active transfers after an uncertain
outcome. WorldCoordinator attempts a server pause after a client resume
failure, including an interruption, but this is no guarantee that clients or
even the server stopped.

Responses and liveness are checked at bounded points in time; there is always
a race after the last check, and acknowledgements are trusted client assertions,
not process identity or proof of uninterrupted state. The current coordinator
pauses the server before clients, and resumes it before clients, so this is not
a simultaneous start or proof of consistent game state. A real client must
integrate its local `LocalParticipantControl`/Lua endpoint with its existing
single X4 update owner, and establish request/receipt lifetime and cleanup.
The existing participant probe is Linux-specific and disposable; Windows and
direct Internet operation remain untested and require separate integration.

`tests/test_authority_experimental_tcp_participants.py` uses a real loopback
TCP channel and synthetic game/clients, including successful pause/resume and
stale, malformed, timeout and disconnect cases. It is not an X4 gameplay test.
