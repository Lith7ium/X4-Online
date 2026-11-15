# Experimental two-X4 TCP integration

`tools/dev/authority_tcp_native_live.py` is an opt-in Linux/Linux diagnostic
built on the existing disposable two-X4 marker harness. Importing it does not
start X4. The host owns a loopback TCP control socket and the existing file
service; it issues a real TCP-bound offer and the cooperative client helper
sends the corresponding marker/load/pause claim over that same connection.
The helper takes exclusive ownership of inherited client TCP and participant
UDP sockets. Its `LocalParticipantControl` sends commands to the isolated
client's X4 Lua endpoint and returns the correlated pause/resume receipts over
TCP. A second loopback connection simulates a join and triggers a native pause;
it is not a second playable client. The experiment stops with a save pending:
it does not test last-player logout or produce a final departure checkpoint.

The child receives the lease, claim and controller details through a private
bounded Unix socket, not its command line. Parent and helper check time and
process identities around operations; the parent also checks protected files.
The synchronous bridge and participant network calls use remaining-time limits,
and an expired or uncertain result is not retried. File-system operations and
the existing save download are not a hard absolute-deadline guarantee. Socket
and identity checks are point-in-time checks rather than continuous fencing.

The helper must be reaped before either X4 instance or the shared lock can be
cleaned up. The base supervisor's optional cleanup hook retains the X4
processes and lock when helper termination cannot be confirmed; communication
sockets are still closed best-effort and the result reports failure. The helper
must not spawn descendants, SIGCHLD must stay at its default, and no competing
handler, thread or native child reaper may reap it. These are caller obligations;
the Python SIGCHLD check cannot rule out native SA_NOCLDWAIT or hidden reapers.

`tests/test_authority_tcp_native_live.py` runs the full hook with a fake engine,
fake UDP X4 endpoint, real loopback TCP/UDP, real helper process and disposable
files. Worker edge cases are in `tests/test_authority_tcp_native_worker.py`;
owned process/lock cleanup is checked separately. Passing them does not prove
the native X4 experiment succeeds. Even a successful isolated native run would
not establish exact consumed bytes, gameplay, a complete shared universe,
Windows, an Internet connection or production security.
