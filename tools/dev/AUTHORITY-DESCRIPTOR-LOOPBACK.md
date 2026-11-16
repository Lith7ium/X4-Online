# Experimental one-shot descriptor over loopback

`authority_descriptor_loopback.py` is an opt-in test component. It opens no
listener, launches no process, runs no X4 code and defines no production wire
protocol. It accepts only a connected IPv4 TCP socket whose local and peer
addresses are both `127.0.0.1`. The caller owns connection setup, ensures the
only socket owner and transfers that socket to the function; both endpoints are
closed by the component on success or failure. Do not retry an ambiguous
exchange. A sender error does not establish that a remote mutation did not
happen.

A single newline-terminated JSON frame is limited to 1024 bytes excluding the
newline; duplicate keys, nonfinite numbers and extra fields are refused. The
exact descriptor fields are `version=1`, `type="descriptor"`, a 32-character
lowercase hex `attempt` and `epoch`, `seq=1`, `index=3`, ASCII `macro`, `sector`
and `owner` names, integer `seed` and numeric `x`, `y`, `z`. Seed is a requested
test value, not a readback of a ship's state. Sector is a macro name, not a
process-local handle or a claim of universal uniqueness. Coordinates are
bounded sector-space test numbers; the component does not establish their
frame or actual game position. Actor and sector handles are not accepted.

The receiver independently checks the expected attempt and epoch, then calls
`inspect(descriptor_copy)`. It sends a correlated ACK only after that callback
returns exactly `True` and after the final deadline, guard and socket checks.
The caller must issue a fresh attempt and consume it once across connections;
the component does not maintain a cross-connection replay ledger. Extra frames
already read or visible at the point of the receiver's check are refused; an
extra frame arriving later is not excluded by this observation.
The caller must implement actual local Create/Inspect, correlate its native
receipt, verify its actor/sector and enforce exclusive ownership of X4 events.
A Python callback's `True` is a caller assertion; this module cannot establish
that X4 inspected anything. A socket check is a point-in-time observation, not
proof of continued connection or delivered ACK. Sending the ACK can succeed
locally even if later processing or delivery fails; the receiver can also fail
its final guard after an ACK was sent. Hence the two peers may disagree about
outcome; fence and discard the disposable case rather than retry.

`send_descriptor(sock, descriptor, deadline, guard)` returns `True` only after
a matching ACK; `receive_descriptor(sock, attempt, epoch, inspect, deadline,
guard)` returns the validated descriptor after attempting its ACK. `deadline`
is an absolute `time.monotonic()` deadline on the same host. The callbacks must
return exactly `True` when successful. Guard, deadlines and socket readiness are
checked before and after blocking I/O and the inspect callback. Calls are
synchronous: this module cannot interrupt a stuck callback or guarantee an
absolute wall-clock upper bound when user code blocks. Any process identities,
Steam identity, protected files, paused game state, deadline, exclusive
session-owner and helper lifecycle are the caller's responsibility. In
particular, a helper must be reaped and its descriptors fenced before owned X4
or lock cleanup. Pause/checks do not make state observations atomic.

Run the focused offline tests with
`python3 -m unittest discover -s tests -p test_authority_descriptor_loopback.py -v`.
They exercise real loopback TCP using fake inspect and fake process state, not
X4, Internet, Windows, authenticated peer identity, collision safety or
multiplayer behavior.
