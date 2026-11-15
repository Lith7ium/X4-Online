# Experimental local host owner

`ExperimentalLocalHost` is an opt-in integration seam for an existing
`WorldCoordinator`, matching `ExperimentalTCPControl` and already-started
loopback `FileService`. It opens no listener and launches no X4 process. A
single exclusive owner accepts only loopback connections with `adopt`, calls
`tick` repeatedly, and serializes all caller-side coordinator, socket and
service operations on the same thread. The file service has its own worker
threads. Each tick pumps the control channel then runs at
most one pending coordinator operation; resume requires the channel's
point-in-time output-drain/liveness gate. A tick can block during synchronous
engine work; the channel cannot be polled while that work is executing.

The owner creates, validates and later stops/fences the real X4 process and
`LocalControlBridge`, listener, control channel and service. This class does not
perform shutdown or guarantee a last-departure save if the caller stops pumping.
After a fault or uncertain operation, the caller must fence or settle all of
them, including active transfers; retrying this owner is not recovery. An empty
session on process restart does not restore a world automatically.

`WorldCoordinator` requires a separate synchronous participant adapter that
confirms each client's pause/resume. The current control channel has no such
commands or receipts; fake participant confirmations in tests are not usable
as client control. A claim that a client loaded the marker is trusted, not
independent proof. The socket gate proves neither remote receipt of an ACK nor
future liveness. The service uses its existing shared token and does not bind a
file request to a particular control connection.

Tests use fake engines and participants with actual loopback sockets and a
disposable checkpoint. One also exercises the actual `LocalControlBridge`
against a synthetic UDP engine. They do not establish native execution, Windows, public
Internet connectivity, playback, or multiplayer gameplay. Loopback is a limit
of this experimental seam, not an architectural choice for the final product.
