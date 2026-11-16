# Experimental census job descriptor over local TCP

`authority_job_descriptor_loopback.py` is a separate, one-shot, opt-in test
transport. Importing it starts no X4 process and opens no socket. Each entry
point consumes one already-connected, exclusively owned IPv4 TCP socket with
both endpoints at `127.0.0.1`, closing it on every outcome. It reuses the
existing bounded JSON stream, timeout and periodic guard primitives; it does
not change the existing index-3 descriptor transport.

The only descriptor is a newline-terminated JSON object with exact fields:

* `version=1`, `type="job_descriptor"`, 32 lowercase hex characters each for
  `attempt` and saved registry `epoch`;
* `transport_sequence=1`, independent `job_sequence` from 1 through 2^53−1,
  and `index=10055`;
* ASCII `macro`, `faction`, `sector_macro` names of 1–128 characters;
* finite numeric sector-frame coordinates `x`, `y`, `z`, each bounded to
  ±10,000,000. Booleans are not accepted as numbers.

A JSON frame is at most 1024 bytes before its newline. Extra/missing fields,
duplicate keys, nonfinite numbers, malformed names and correlation mismatches
are refused. Actor handles, local sector handles and seed fields are not
accepted. Names and coordinates are only data from the caller; they do not by
themselves establish ship identity or equivalence of sector frames.

`send_descriptor(sock, descriptor, deadline, guard)` sends one frame and
requires a witness ACK matching `attempt`, `epoch`, both distinct sequence
numbers and index. The receiver uses
`receive_descriptor(sock, expected_attempt, expected_epoch, expected_job_sequence,
witness_check, deadline, guard)`: it validates that expected context, invokes
`witness_check` on a copy, then rechecks the deadline, guard and socket before
sending the ACK. Only an exact Python `True` is accepted from that callback.
The callback must perform and correlate the actual client-local witness
inspection; this transport cannot prove it did so. An ACK confirms only that
the callback and surrounding checks succeeded locally, not object creation,
reconciliation, complete delivery, native frame identity or gameplay.

The deadline is an absolute `time.monotonic()` time on the same host. The
injected guard must independently fence the source and client processes,
paused states, event queue, protected files and timing; callbacks are
synchronous and cannot be preempted if stuck. Peer-quiet checks are sampled.
An ACK send can succeed locally before a later failure or lost delivery, so
both peers can disagree; never retry an ambiguous exchange. The caller must
ensure a fresh attempt is consumed once across all connections, reap any
helper before releasing owned X4 processes or their lock, and fence late
callbacks and logs. This component has no replay ledger, authentication,
Internet connection, save operation or ship Create capability.

The focused tests use real loopback TCP with synthetic witness checks and
process guards. They do not run X4 or prove Windows, Internet, exact loaded
bytes, runtime sector binding, queue continuity or multiplayer:

```
python3 -m unittest discover -s tests -p test_authority_job_descriptor_loopback.py -v
```
