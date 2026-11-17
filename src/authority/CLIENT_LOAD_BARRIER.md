# Experimental client load observations

`lua/client_load_barrier.lua` and `lua/x4_client_load_engine.lua` are opt-in
building blocks. Loading them registers nothing and starts no X4 action. No
production launcher or deployed network session currently uses them; isolated
Linux diagnostics use them under a dedicated supervisor.

For an isolated experiment, a trusted supervisor must create a fresh, private,
immutable UI configuration before starting one exclusively controlled X4
process. It supplies a unique `attempt_id` and the exact coordinator offer
fields (`world_epoch`, `connection_handle`, `baseline_id`, `load_generation`,
`checkpoint_id`, `sha256`) and the already staged `save_###` slot as
`ticket`. The complete ticket is copied by the component. The owner must
refresh the save list with the adapter and wait until it is loaded. Calling
`begin()` in the start menu emits `load_requested` and calls X4 `LoadGame`.
The event precedes the call, so it is only an attempt, never success.

X4 rebuilds Lua after `LoadGame`. The experiment must re-read the same protected
configuration and explicitly call `observe_pause()` in the new UI. Once it sees
a valid player outside the start menu, the component requests pause at most once
and waits until X4 reports the game paused. It then emits `pause_observed` and
the configured ticket. It never unpauses. The supervisor, not Lua, must verify
that the configuration remained unchanged, both ordered events came from the
same still-owned process, the events match the outstanding offer and attempt,
and no other load or game activity interfered. It must reject old or duplicate
events. A pause observation by itself does not show that `LoadGame` succeeded,
which file X4 consumed, that no simulation occurred before the pause, or that
the loaded universe matches the checkpoint.

These primitives provide no authenticated event transport or independent
cross-reload proof. The isolated supervisor treats its correlated observations as
trusted assertions for experimental admission, not as proof of the loaded file.
A production integration still needs controlled save staging, process
and event fencing, ordered observations, client compatibility checks, a policy
for already connected clients, and a verified resume protocol. The configuration
approach is limited to an isolated process started for one attempt; it does not
design dynamic rejoining of a running client.

`tests/test_authority_client_load_barrier.py` runs Lua with test doubles only.
A separate isolated Linux X4 run combined this barrier with a localhost download;
see [the native experiment](../../docs/AUTHORITY-CLIENT-DOWNLOAD-LOAD.md). It
does not establish Windows behavior or actual client admission.

## Experimental single-thread client owner

`experimental_client_owner.py` composes the existing remote load client with
`ExperimentalTCPParticipantClient` on one owner thread. After the server accepts
the load claim, it transfers the same connected socket once to the participant
adapter. The owner validates the known participant prerequisites before making
the claim, closes the socket on failure or explicit close, and rejects calls
from other threads. If admission succeeds but the later handoff fails, the
server may already consider the client admitted; the caller must treat that
outcome as uncertain and must not retry the claim automatically.

The caller still owns transport authentication, private staging paths, the X4
process and its identity, ordered load/marker/pause observations, and a bounded
pause/resume controller. Observations passed to the owner are trusted caller
assertions, not independently verified game events. While waiting for them, the
caller must pump the load connection often enough when keepalive is enabled.
There is no Windows process integration or real-X4 validation of this owner,
no authenticated X4 event channel, and no proof of which file X4 reads. The
owner has no production launcher integration and does not establish gameplay. Focused local tests use
real wire and file-service components with simulated X4 observations and
controller results; they do not establish native Windows or Internet behavior.

`lockstep.launcher.profile.prepare_fresh` is a separate helper for a future
launcher: it requires an exclusively controlled existing root and creates only
an absent disposable profile, without deleting or overwriting an existing one.
The caller remains responsible for the root's ancestors and for preventing
concurrent directory replacement. It is not yet wired into an authority
launcher. In one isolated Windows Python 3.14.8/Wine run, a synthetic new
profile was created and an existing synthetic profile, including its save
sentinel, was left unchanged. Native Windows, real junctions and X4 were not
tested by that run. Its private output is
`.local/fresh-profile-wine-20261117-01/`.

## Opt-in Linux recovered-server diagnostic

`tools/dev/authority_recovered_loopback_server.py` accepts
`--diagnostic-client --diagnostic-single-owner` for one private, load-only
client. The existing diagnostic TLS certificate and key options may also be
used. This branch does not support registry/witness or motion diagnostics;
without the new option the previous client path remains selected.

`authority_recovered_owner_client.py` supervises a single
`authority_client_owner_worker.py` child. The child retains the same TCP
connection through download, admission and participant control. The supervisor
owns X4 processes, protected files, correlated log observations and the UDP
controller until it has enrolled and paused the client; it then closes its UDP
copy before explicitly handing the controller state to the child. The staged
file is made read-only before its verification fingerprint is recorded. The
recovery checkpoint must exist and the offered checkpoint ID and marker must
both differ from it.

The supervisor pumps the control connection and rechecks its guarded context
while waiting for the child, including fragmented IPC frames. During the
synchronous participant resume exchange, the recovered-server adapter uses
the client, server, protected-file and TLS guards. These are checks at guarded
points: a single blocking filesystem or native call cannot be interrupted by
them. If a claim or command may already have been dispatched when a failure
occurs, its effect is indeterminate; the supervisor must fence and reap the
child before releasing X4 or its lock, and must not retry the claim as though it
never happened. A successful child STOP alone does not prove a final save.

`tests/test_authority_client_owner_worker.py` and
`tests/test_authority_recovered_owner_client.py` exercise real local child,
file-service, TCP/UDP and TLS components with simulated X4 process, log and
controller observations, including guard failure during admission and resume.
The single-owner recovered-server path has **not** been validated with real X4;
the earlier real two-X4 TLS load used a different client-owner path. Neither
these tests nor the earlier run establish Windows, Internet or gameplay support.

On 2026-11-17 an isolated native Linux attempt planned with two X4 instances
and the single-owner TLS option was stopped during server startup after
prolonged lack of progress before any Vulkan initialization log entry. The client did not start, so this
attempt provides no real-X4 evidence for the owner or TLS path. The cause remains
unknown. The supervisor reported its owned processes stopped without cleanup
errors; the test lock and temporary private key were absent afterward, and no
X4 process remained. The local artifacts are under
`.local/owner-real-tls-20261117-run01/` and
`.local/owner-real-tls-20261117-evidence01/`. These results do not establish
Windows, Internet, gameplay, or persistent multiplayer behavior.

A second instrumented attempt, `.local/owner-startup-observed-20261117-01/`,
was stopped after more than four minutes without server-log progress. It also
did not start a client. Six observations recorded waiting threads and an X11
display whose connected DP-2 output reported DPMS off; these observations do
not establish why X4 stalled. The run reported cleanup and temporary-key
removal; no X4 process or endpoint remained. Separate X11 and Vulkan queries
succeeded in an X4-like isolated namespace, but did not start X4 or prove that
X4 could create and present a swapchain.

The associated repository check reported 4,623 tests without failures and
56 skips; it was incomplete and must not be presented as a complete passing
check. A later check covering the diagnostic timing and fresh-profile helper
ran 4,632 tests without test failures, but still skipped 56 checks and therefore
remains incomplete.
