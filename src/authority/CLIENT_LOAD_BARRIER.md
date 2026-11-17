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

## Experimental Windows process owner

`experimental_windows_owned_process.py` is a separate process-lifecycle
experiment. It is not integrated with X4: its start window can leave an
untracked process if `Popen` is interrupted, so it must not be used to launch
X4 until that gap is controlled and demonstrated. It does not establish a
process tree, log source, executable identity or profile ownership.

On 2026-11-17, one private Windows-Python-under-Wine run observed exit code 7
from a synthetic child and used the retained process handle to terminate and
observe exit from a second synthetic child. The overall probe reported failure:
its private wineserver stop and wait returned successfully, but the subsequent
point-in-time prefix-process scan could not inspect some same-user `/proc`
entries, so its bounded cleanup checks were not confirmed. No complete process
tree cleanup is proven. The result is recorded under
`.local/windows-owned-process-wine-20261117-01/`. This is not evidence of
native Windows, X4 startup, profile safety or multiplayer behavior.
The associated full check ran 4,644 tests without test failures, but remained
incomplete because 56 checks were skipped.

A separate synthetic experiment tested `CreateProcessW` with a private job
in the creation attribute list under Windows Python in Wine. In both runs 02
and 03, the suspended test process was observed in the job before its first
thread was resumed. Run 02 could not check the test grandchild: its process
handle requested `PROCESS_QUERY_LIMITED_INFORMATION` and `IsProcessInJob`
failed with error 5. Run 03 compared two simultaneously held handles for the
same live synthetic grandchild: the limited query again failed with error 5,
while a handle with `PROCESS_QUERY_INFORMATION` confirmed job membership.
[Microsoft documents](https://learn.microsoft.com/en-us/windows/win32/api/jobapi/nf-jobapi-isprocessinjob)
either query right as sufficient for this API; current [upstream Wine source](https://raw.githubusercontent.com/wine-mirror/wine/master/server/process.c)
requires the latter. The exact source of the tested Wine build was not verified.
The result is evidence for this Wine run, not for native Windows behavior.

Run 03 terminated its private job and observed both test-process handles
signaled. Run 02 also observed both handles signaled during failure cleanup.
Each private wineserver stop and wait reported no error, but the subsequent
prefix-process scans were incomplete despite finding no visible matching
processes; complete cleanup is not confirmed. The local results are in
`.local/windows-job-list-wine-20261117-02/` and
`.local/windows-job-list-wine-20261117-03/`. These runs did not launch X4, test
creator termination during `CreateProcessW`, establish general process-tree
containment or cleanup, or make the existing X4 process owner safe to use.

A further private Wine probe, `.local/windows-job-death-wine-20261117-01/`,
tested abrupt termination of a synthetic job creator after it had started a
job member and that member's child. The Windows-Python observer reported that
it held and validated both process handles before terminating its own creator;
it then observed both process handles signal without its individual-process
fallback. Job membership and transfer of process handles without the job
handle follow from the reviewed probe path; no independent OS trace was taken.
The Windows-Python portion reported success, but the Linux wrapper reported
failure because the prefix-process scan was incomplete, even though it found
no visible matching processes. The private wineserver stop and wait reported
no error; complete cleanup is not confirmed. This was not native Windows or X4
and did not test creator death during `CreateProcessW`, Steam interactions,
general process-tree containment, or recovery of a real profile.

## Windows fixture overlay installer

`experimental_windows_fixture_overlay.install_fixture_overlay` can populate an
absent `extensions/x4_lan_lab` inside a caller-owned new disposable Windows
view. It assembles the existing load, marker, identity-fixture and local UDP
participant probes. The caller supplies a marker-bound offer, the expected
profile-45841 save path, a local participant port and lease, and an explicit
Windows network DLL path with an independently trusted SHA-256. The expected
marker is not written to the client configuration. The returned file hashes
are a snapshot for the caller to guard; they do not guard files by themselves.

This installer is **only for diagnostic saves containing the two existing
identity-fixture ships and checkpoint marker**. It is not a general-world
installer or launcher; the fixture probe will reject saves without those ships.
The supplied save path is checked only for syntax: a path ending in
`45841/save` can name an ordinary profile. Before installation and X4 startup,
the supervisor must independently establish the physical identity of the
intended private profile. It must own the view, profile and their ancestors,
protect the staged save, ensure files remain unchanged, and bind observations
to the same live X4 process. The participant UDP probe may listen before the
marker and identity checks complete. The supervisor must withhold commands
until those observations are correlated and admission is confirmed.

The generated configuration contains the ticket and lease in plaintext. The
supervisor must protect it with private ACLs and clean up its owned copy after
X4 stops. Filesystem checks cannot fence concurrent replacement. On failure
after creation, a partial extension remains for inspection; no existing
extension is deleted or overwritten. Save paths are currently ASCII only.
The focused tests use synthetic files on Linux; this installer has not been
used with a Windows X4 process and does not establish gameplay or Internet use.

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

An independent headless display experiment later combined a private PID-1
reaper, Cage, Xwayland, GLES2 and one AMD render node without exposing a KMS
card node. In `.local/private-pid1-gles2-vulkan-20261117-01/`, the X11 probe
connected and `vulkaninfo` reported XCB, Xlib and Wayland surface capabilities;
the reported GPU renderer was the Radeon RX 7900 XTX. The test reported
cleanup and removed its empty private Xauthority file, under its documented
exclusive PID-namespace membership assumption. It did not establish that
Xauthority authentication was enforced, that a frame was presented, that the
host monitor was unaffected, or that X4 can run in this display environment.

Separately, `.local/private-unix-netns-20261117-02/` recorded a nonce-bound
exchange over a private bind-mounted Unix pathname socket across network
namespaces. A random host-namespace abstract-socket sentinel was unreachable
from the private namespace, and the test reported process and socket cleanup.
This demonstrates only those generic socket operations; it does not establish
X11 transport selection or authentication, Steam/UDP connectivity, Vulkan
presentation, or X4 operation. The cleanup result depends on the experiment's
explicit exclusive PID-namespace membership assumption.

An optional Linux diagnostic guard now checks a host-network UDP socket inherited
by a process in another network namespace. It pins the process and both
connected socket endpoints, samples their identities and checks for matching
IPv4 and IPv6 socket port usage. The synthetic tests exercise bidirectional
datagrams and competing sockets, including wildcard bindings and IP_PKTINFO.
The guard assumes cooperative ownership and
does not prevent changes between checks; its caller must fence the session on
failure. It is not connected to the X4 launcher or game bridge. Passing a file
descriptor through the sandbox was also exercised with a synthetic process, but
X4 startup, Steam connectivity and socket adoption remain untested.

The existing local participant peer check also rejects any additional IPv4 or
IPv6 UDP socket using the observed sender port in the peer's network namespace.
This closes reproduced cases in which another local socket could send using the
same apparent source. It can also reject harmless sockets on other interfaces;
it remains a sampled check and the caller must separately own the receiver.

A separate private Cage/Xwayland menu attempt used a fresh profile with an
empty read-only save directory and hid the installed extensions. X4 started,
but no engine log or start-menu receipt appeared within 120 seconds. Its
stdout reported a closed X connection during shutdown; that does not explain
the earlier stall. The private PID-namespace reaper reported cleanup, and the
save directory remained empty. Under the experiment's exclusive-namespace and
test-directory assumptions, no X4 process remained afterward. This attempt did
not establish a working display, the reason for the stall, or game networking.
Its local result is `.local/private-x4-menu-real-20261117-01/result.json`.

An additional synthetic display probe with a process-wide file-size limit
terminated Cage with `SIGXFSZ`. The observed test PIDs exited, but the result
directory was removed before an empty-namespace receipt could be retained and
the later process scan was incomplete. Full cleanup was therefore not
independently confirmed. The limited harness is disabled for real X4; the local
report is `.local/private-x4-menu-output-limit-failure-20261117.md`.

Two repository checks ran 4,664 and 4,677 tests respectively, each with one
error in a source-motion UDP handshake test and 56 skipped checks. Their shared
error message did not distinguish a mismatched packet from a failed ownership
check. Targeted reruns passed, but the original failures remain unexplained. The
direct worker now reports separate fixed diagnostic categories without packet
contents or tokens; its process-level result remains intentionally generic.
A subsequent check ran 4,681 tests without test failures, but still skipped 56
checks and therefore remains incomplete under the repository's check policy.
After preparing locally available pinned X4 executables, Zig, the wire-crypto
library and game schemas, an expanded check ran the same 4,681 tests without
test failures and with 27 skips. It remains incomplete: some checks require
Windows, while others need reference files not available in the partial local
view. The local prerequisite details and log are in
`.local/check-prerequisites-20261117-01/` and
`.local/check-expanded-prerequisites-20261117.log`.

The associated repository check reported 4,623 tests without failures and
56 skips; it was incomplete and must not be presented as a complete passing
check. A later check covering the diagnostic timing and fresh-profile helper
ran 4,632 tests without test failures, but still skipped 56 checks and therefore
remains incomplete.
