# Proposed isolated TCP/native integration test

The existing two-X4 marker harness can exercise the TCP participant path
without choosing a permanent process architecture. This design has not been
implemented or run against X4. `authority_helper_lifecycle.py` only provides a
separately tested lifecycle primitive for one trusted Linux helper that never
forks; it is not an integrated test runner.

The supervisor remains the exclusive host-side socket owner. Its existing
`join(world)` hook would create the TCP connection and use `host.adopt`, while
`offer_and_download` would obtain the actual encoded offer over that socket,
then stage and verify the offered save. After the existing load/marker/pause
evidence, the supervisor would enroll the local X4 participant controller,
establish process and protected-file guards, and transfer exclusive ownership
of the client TCP socket and participant UDP socket to the helper. Inherited
private file descriptors, rather than command-line arguments or public files,
must carry the lease, peer, epoch, load claim and controller sequence. The
helper would send the real claim, read exactly the accepted line, and pump
`ExperimentalTCPParticipantClient` backed by `LocalParticipantControl`.

The parent must guard both X4 process identities and the absolute deadline
before and after each native operation, including the TCP claim acceptance;
the helper must independently guard its own participant operation and report
errors over bounded, private IPC. The process guard does not prove bytes X4
actually consumed, uninterrupted liveness, or client authenticity. Both
sides need explicit, coordinated deadlines; neither may retry an uncertain
pause/resume. Controller and file operations can block, so the parent must be
able to kill and reap the helper before proceeding to X4 or lock cleanup.

For a last-departure diagnostic, a second adopted loopback TCP connection can
trigger native pause of the first participant. After the second connection is
removed and the first resumes, the helper can deliberately disconnect. The
parent must observe the actual EOF, drive native server pause and a fresh
marker-bound save, and verify the confirmed checkpoint identity. This is a
simulated disconnection, not a test of the game's logout UI.

The present harness cleanup runs inside `base.run` before the wrapper regains
control. Therefore a future integration must arrange helper termination and
reap within the active hook's own `finally`, with signal-safe registration
before launch. On unconfirmed helper stop, it must retain the shared X4 lock
and avoid claiming cleanup success. A bounded join of a Python thread is not
equivalent to terminating a process and does not satisfy this contract.
`OwnedHelper` accepts an owner-maintained registry before spawning, gates exec,
uses a pidfd for signals and reaps the exact child; its tests cover gating,
SIGTERM-resistant child termination and a failed pidfd setup. It does not
terminate descendants, protect inherited credentials, implement IPC, verify
X4, or itself integrate with the harness. An interrupted release can have
briefly run the helper; the owner must still stop and reap it.
The lifecycle primitive requires default `SIGCHLD` handling, with no competing
handler, thread or library reaping this child. That caller contract is necessary
to bind the initial spawned PID to its pidfd; later external reaping is refused
when observed rather than reported as a successful cleanup. Python's signal
disposition check cannot independently rule out native `SA_NOCLDWAIT` or a
foreign child reaper; excluding both is part of the caller's contract.
