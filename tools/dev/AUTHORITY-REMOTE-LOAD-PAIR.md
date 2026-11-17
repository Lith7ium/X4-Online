# Isolated remote-load owner experiment

`authority_remote_load_pair_live.py` is an opt-in Linux/Linux diagnostic using
the existing private, disposable two-X4 supervisor. Importing it starts no game.
A fresh pidfd-owned helper exclusively owns the connected loopback TCP stream
from offer through download, staging, cooperative claim, and server acceptance.
It uses `ExperimentalRemoteLoadClient` and pumps its keepalive while waiting for
the supervisor. The host is polled during transfer, save hashing and the existing
X4 startup/load observation loop.

The supervisor requires the existing ordered ticket-bound load request, saved
marker after the MD load event, and pause observation; it also checks protected
files and the two owned process identities. It separately confirms pause before
instructing the helper to submit its claim. The helper then transfers the accepted
socket via a private Unix socket. The supervisor waits for successful helper exit
before passing the socket to the existing participant-control helper, which does
not submit another claim. Helpers are stopped before the isolated X4 process
locks are released. An uncertain admission or cleanup is not treated as success.

The keepalive response timeout is 300 seconds and remains bounded by the overall
attempt deadline. Some supervisor operations (individual filesystem calls,
installation, process startup, enrollment and synchronous pause exchanges) do
not pump the host and cannot be interrupted here. If they block too long the
attempt fails; this does not establish uninterrupted keepalive for arbitrary
loads. Observations are cooperative and do not prove exact bytes read by X4,
continuous pause, or no simulation between loading and pause. The file service,
TCP, Unix FD passing, process fencing and profiles are for a controlled Linux
loopback experiment, not a Windows client, Internet launch path or gameplay.

Offline tests use real localhost sockets and helper subprocesses but simulated
X4 events. The owner now copies the download to a new save slot, makes the
copy read-only, and verifies it before requesting the load. The separate
download remains in the private output directory and requires additional
space. A failed copy may leave an incomplete private target for inspection.
This revised copy path has not yet been exercised in native X4.

## Bounded native observation, 2026-11-16

The earlier isolated Linux/Linux run `.local/authority-remote-load-pair-01`,
which staged with a hard link rather than the current copy path, reports
successful checkpoint transfer, trusted client admission, TCP participant
commands and confirmed server/client resume. Its result reports clean helper
exit, no remaining owned processes and confirmed owned-process cleanup. These
TCP and resume statements are supervisor results, not independent packet
captures or independently reconstructed native control receipts.

The client's X4 log separately records the ticketed load request, inspection
of marker `01f60a652debf75ef7006280335a71f9`, and ticketed pause observation in
that order. The two fixture names and macros appear in both X4 logs; their local
object IDs differ. The stored checkpoint, the server's private save and the
client's staged save all have SHA-256
`0cba465372f04ba98f7a4e961dddceacb2f19568d8b74205acf6ad1629e6d2a9`.
The result reports a matching open save descriptor and observed maximum offset
25,512,850 bytes; this point observation does not prove that X4 consumed every
byte, or the absence of game advancement before pause.

The run does not independently record keepalive packets or establish survival
of a deliberately prolonged load. It uses loopback, two isolated Linux X4
processes and a cooperative claim. It does not establish Windows operation,
an Internet connection, gameplay or a persistent multiplayer session.
