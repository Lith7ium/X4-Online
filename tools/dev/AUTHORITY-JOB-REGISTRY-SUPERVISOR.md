# Isolated job-observation supervisor contract

`authority_job_registry_supervisor.py` is a tested lifecycle component, not an
executable X4 runner. It opens no sockets, prepares no profile, launches no
process and does not create a display. Its caller must first build a private
X4 case with an isolated 45841 profile, a virtual display, a fenced owned
process and an exclusive bridge. It must also supply a local channel that
starts and receives responses from `authority_job_registry_host.lua`; this
channel and the runner that connects these pieces do not exist yet. The normal
user profile and saves must never be mounted writable.

For one exclusively owned instance, `supervise` requests a confirmed pause,
confirmed resume, one host start and its ordered response stream, then a
separate confirmed pause before owned-process cleanup. Event identities must
match the current epoch and sequence, and the final summary must account for
every acknowledged local event. Zero events are inconclusive. An exception,
missing response, changed process identity, clock regression, unconfirmed
pause or uncertain cleanup prevents a successful result. On uncertain resume
the caller-provided cleanup must terminate only the fenced owned process;
there is no retry or recovery from that diagnostic case.

The channel must have bounded operations and independently validate its own
endpoint, lease and callback ordering. The bridge's individual blocking
operations must also have bounded timeouts. The caller supplies
`bridge_timeout`, which must match the bridge's configured `_timeout`; before
each bridge operation the supervisor requires more than that timeout plus one
second remaining. Channel receive is limited to the remaining time after this
reserve. No extra thread interrupts a blocked bridge; the caller still owns
the guarantees for dispatch, channel start/receive and cleanup themselves.
`check_owner` must verify the original process and Steam identities;
`cleanup` must stop only that owned process and report whether any remain.
The eventual runner must arrange cleanup independently around construction and
setup failures, as well as close its sockets. Fake lifecycle tests do not
establish isolation, a native pause, native events, a complete world, creation
or delivery to a client.

Results include at most 4096 validated local event records, each containing
only sequence, registry index and classification; exceeding that bound fails
the diagnostic. They contain neither local actor identities nor leases.

The summary validator checks basic index/classification consistency against
the baseline count and rejects repeated new allocations. It cannot independently
prove which native object a row refers to, or that the host and its channel
reported all events. `checkpoint_requested=false` means this supervisor made
no checkpoint request; it does not prove that no other save occurred.
