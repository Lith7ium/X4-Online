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
it is not a second playable client. By default the experiment stops with a save
pending. The opt-in `--last-disconnect` variant removes that second connection,
completes the pending save, resumes the remaining client and then stops the
client helper. After observing the actual TCP EOF, the owner drives a new server
pause and save, then checks that the confirmed checkpoint has a fresh marker in
its saved bytes and no remaining players or offers. This is a simulated control
disconnect: client X4 remains running until harness cleanup, so it is not a
game logout or proof that the client stopped. Restart/reload is not exercised.

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
files. It includes the last-disconnect variant, delayed EOF processing, an
uncertain final save and explicit EOF checking. Worker edge cases are in
`tests/test_authority_tcp_native_worker.py`;
owned process/lock cleanup is checked separately. Passing them does not prove
the native X4 experiment succeeds. Even a successful isolated native run would
not establish exact consumed bytes, gameplay, a complete shared universe,
Windows, an Internet connection or production security.

On 2026-11-15, one isolated Linux/Linux run completed successfully. The server
created the marked checkpoint and transferred it locally; the second X4 process
reported loading and pause. The trusted load claim and participant commands used
the TCP path, and both native processes confirmed resume and the later pause.
The second join was simulated, the next save remained pending, and the helper
exited cleanly before owned-process cleanup reported no remaining processes.
This result is limited to the diagnostic conditions and exclusions above.
