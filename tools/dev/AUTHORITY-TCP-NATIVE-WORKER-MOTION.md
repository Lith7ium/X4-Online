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
participant controller confirmed resume; it fences motion before issuing a
pause and rejects it until another confirmed resume. At the first motion
request it binds a separately leased UDP peer, checks the expected client
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
