# Opt-in motion callback on the native participant worker

`authority_tcp_native_worker.py` keeps the existing three-FD behavior by default.
The optional fourth FD is a distinct, unconnected, bound loopback UDP socket.
The private configuration must then contain `motion` with exactly `lease`,
`attempt`, `epoch`, `generation` and `timeout`; tokens are lowercase 128-bit
hex. Motion timeout must be positive, at most 30 seconds, and less than half
the participant controller timeout, leaving room for a first READY and BIND.
A motion lease or attempt must also differ from the TCP claim attempt ID.
A config without its FD or an FD without the config is refused. The supervisor
must still fence FD ownership across process handoff and retain the profile
lock until all involved processes stop.

There is still one TCP reader. The worker accepts motion only after its local
participant controller confirmed resume. Before dispatching a pause it requires
a correlated local STOPPED receipt, including when no sample was sent. A pause
before the first resume fails closed. The stopped lease cannot be resumed;
another motion session needs a fresh owner and lease, which is not implemented.
This once-only prototype is not approved for recovery-session integration: a
normal join pauses existing participants and later requires them to resume.
Worker shutdown likewise requires STOPPED even if no sample was bound;
shutdown before the first resume fails rather than claiming a remote stop.
At the first motion request (or stop) it binds a separately leased UDP peer, checks the expected client
process and sampled socket inode, and waits for correlated local binding and
buffer acceptance. A stop, lost peer, invalid context, unsupported despawn or
uncertain operation faults the worker. Cleanup attempts all owners, and an
uncertain stop must be fenced by the supervisor. These sampled checks are not
atomic authentication, guarantee of continuous pause, or proof of X4 state.

`tests/test_authority_tcp_native_worker_motion.py` uses real local sockets,
the actual worker and Lua saved-baseline binder, and fake X4 ABI/MD. It covers
two samples, PID/UDP ownership, alias rejection and motion fencing at pause.
It does not start X4, show a visible update, establish native velocities,
implement source sampling, interest, Windows or internet operation. The normal
recovered-server supervisor does not yet install the motion owner or pass the
fourth FD; the opt-in is not an end-to-end gameplay path.

Client STOP is separately opt-in on the Lua and Python owners. The Lua owner
accepts STOP only while idle, closes bound references and requires its supplied
router-stop callback to succeed before the correlated STOPPED receipt. A late
UDP packet or MD event faults the stopped owner. The containing X4 update/event
owner must continue checking and propagating such faults after STOP, including
while paused; the current recovery integration does not provide that path.
STOPPED is a sampled cooperative assertion, not proof that no future event or
packet can occur. The host must drain motion before dispatching pause and fence
all processes after uncertainty. This remains offline-tested instrumentation.
