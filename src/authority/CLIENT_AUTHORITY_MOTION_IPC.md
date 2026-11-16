# Experimental client motion UDP pull

`experimental_client_authority_motion_ipc.py` is a default-off, read-only
diagnostic for the explicitly granted saved index 1318 in the pinned test
sector and baseline 10054. The caller supplies a loopback UDP socket already
connected and handed off after the source-motion HELLO/BOUND/ATTACHED wire
handshake. The existing `ExperimentalSourceJobBinding` contract requires a
paused X4 source. The separately enabled `tools/dev/authority_client_authority_bind.py`
factory provides a running-client handshake with external running and grant
guards and PID/start/inode checks; these are sampled assertions. The caller
must keep exclusive access to the socket throughout the handshake-to-bridge
handoff: the owner registry transfer is not atomic. The bridge then claims
that socket object in the shared source-IPC owner registry. Raw or duplicated
descriptors outside this API remain the caller's responsibility.

The mandatory `guard`, `validate_peer(peer)`, and
`grant(epoch, generation, incarnation, index)` callbacks are checked throughout
every operation. They are external assertions: the bridge does not establish
the client's PID, UDP inode, checkpoint, cross-process object identity or actual
high-attention authority. The owner must independently bind these assertions to
the admitted connection and client-X4 process, including their incarnations.
Guards and socket checks are sampled, not atomic or same-user authentication.

`register_saved()` uses the existing `REGISTER_SAVED` / `SAVED_REGISTERED`
wire once. Thereafter `pull()` returns a validated sample or `None` for the
correlated `NO_SAMPLE` response. UDP request numbers strictly increase; emitted
samples must use the configured epoch/generation, fixed index/sector, exact
consecutive sample sequence and strictly increasing client game time. The
first velocity is unknown; subsequent vectors are range-checked but are not
independently proven or converted to server time. Actor handles never enter a
packet. Unexpected data, replay, grant loss, reentrancy or timeout fails and
closes the bridge; there is no retry, job acknowledgement or game write. After
an uncertain send/response the supervisor must fence the associated session.

The caller must ensure each returned sample arose from a matching PULL and a
completed local MD/FFI reader callback; this bridge cannot verify the remote
owner's implementation. Tests use real loopback UDP with a simulated X4 peer;
they do not establish native game behavior, multiplayer, WAN or Windows support.
