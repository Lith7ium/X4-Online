# X4 multiplayer: handover for Astra

Latest client evidence: the shared control path also passed in Windows X4
under Proton using the same source checkpoint, 25 synthetic motion updates,
20 m measured displacement, correlated STOP/release, then pause and clean
owned shutdown. The planned five-second trajectory took longer; cached pose
times span 9.8218675 game seconds, with delay cause unmeasured. No server/TLS or
native-Windows run was involved. See the
[Windows shared-control evidence](AUTHORITY-CLIENT-PLAYBACK-20261117.md#windows-shared-control-smoke-under-proton-2026-11-18).
The user has now approved once-only initial placement at the server position
with native readback on the isolated fixture, retaining the subsequent 50 m
correction bound. That implementation is the next step; clock mapping remains
an open decision. GPU-free server work stays deferred in favor of clients.

Latest client implementation: shared Linux/Windows overlays now accept the
explicit `saved_replica_control_fixture="recovery_enh_870"` option alongside
the existing playback fixture. It prepares the one local NPC after read-only
binding, delays playback until preparation is confirmed, and defers STOPPED
until drained playback and asynchronous local AI-order release are confirmed.
The ordinary binder remains read-only and the option defaults off. This is a
bounded internal fixture, not a general NPC authority policy. See the
[shared control implementation and limits](AUTHORITY-CLIENT-PLAYBACK-20261117.md#shared-fixture-control-option).
Focused fake-engine/configuration checks cover the new path. A subsequent
single Linux X4 run of `e1cdd201` passed: 25 synthetic trajectory updates,
20 m displacement, confirmed STOP/release followed by a real pause, and clean
scoped exit. The shared acknowledgment gate supplies the release evidence;
intermediate MD responses and later autonomous movement were not independently
recorded. See the [native shared-control evidence](AUTHORITY-CLIENT-PLAYBACK-20261117.md#native-shared-control-smoke-2026-11-18).
The later Windows-under-Proton run is recorded above; actual source-X4 motion
remains unproven. Neither runtime check changed initial alignment, clock basis,
server architecture or normal profiles.

Latest client/server evidence: pair 02 passed with actual Linux server X4 and
Windows X4 under Proton using existing authenticated loopback TLS/file transfer,
real checkpoint admission and one server-directed resume. The client retained
50 raw clock samples; 20 final unpaused samples advanced 3.8689934 game seconds.
The server ended paused with a confirmed fresh checkpoint and clean owned exit.
The parent stopped it soon after client exit, so departure and shutdown saving
were not independently timed. Pair 01 failed before Windows launch on a legitimate
Steam DLL symlink; private runtime validation now runs before server launch.
See [TLS admission evidence and limits](AUTHORITY-WINDOWS-LINUX-TLS-ADMISSION-20261118.md).
No motion/WAN/native-Windows/gameplay proof; initial-placement/clock decisions remain pending.

Previous standalone client control evidence: actual Windows X4 under Proton completed one
existing UDP resume (request 1) and pause (request 2) cycle after correlated
marker/identity/registry/load-pause observations. Attempt 03 passed with 34 raw
clock samples: 3.9011855s game-time advance and a final 0.4027788s stable paused
interval. Attempts 01/02 failed before commands due to private process-discovery
assumptions: thread name and incompatible maps/stat device representations.
The corrected check retains pinned map inode plus namespace pathname stat
identity, private prefix and socket ownership. All attempts recorded scoped
cleanup and unchanged source/Steam identities. See the
[control evidence and exact artifact hashes](AUTHORITY-WINDOWS-ENGINE-CONTROL-20261118.md).
That standalone control run used a locally generated offer and did not exercise
real server/TLS/admission or native Windows. Initial-placement/clock decisions
remain pending; no motion changes or full-suite repeat.

Previous load evidence: actual Windows X4 under Proton loaded the native05
checkpoint and returned its marker, both identity fixtures, the 10,082-entry
registry header and pause receipt. The first attempt exposed the Windows
overlay's obsolete `Store.$marker` script; it now installs the shared persistent
`MarkerState.$marker` definition used by Linux. The targeted regression failed
before the fix; 17 focused tests and one corrected engine-load run passed.
Both engine runs used new private prefixes and recorded scoped owned cleanup,
unchanged source hashes and unchanged Steam identities. No full-suite repeat.
See [the engine-load evidence and limits](AUTHORITY-WINDOWS-ENGINE-LOAD-20261118.md).
This was a Linux-owned load diagnostic with a locally generated offer, not the
assembled Windows CLI, native Windows, actual server admission or gameplay.
GPU-free server work remains deferred; initial placement and clock decisions
remain pending. Do not repeat the same load proof without a new reason.

Previous independent Windows prerequisite: the current network DLL actually
loaded through `package.loadlib` in the installed Windows LuaJIT runtime under
Wine. One bounded process passed all ten module/UDP/clock/close checks and
exited zero. The outer private-prefix harness recorded failure because several
same-user process environments were unreadable, leaving its cleanup condition
unconfirmed; no matching prefix process or readable Wine executable candidate
was found. Do not relabel that outer run as passing. The test was not repeated.
No X4, Steam, profile/save, native Windows, WAN or full-suite test was started.
The new portable no-game probe is `tools/dev/authority_windows_network_smoke.py`;
evidence, input hashes and boundaries are in the
[network runtime record](AUTHORITY-WINDOWS-NETWORK-BUILD-20261118.md#real-dll-execution-under-wine).
The initial-placement decision below remains pending and no behavior changed.

Previous read-only follow-up: source setup occurs after the world is running;
saved-client actor takeover starts only on the first BIND. Native05 reads
INITIAL after its private Wait/zero-velocity steps, leaving earlier client
displacement unmeasured. Its initial 88m refusal precedes buffered playback,
so the separate clock-rate issue did not generate that comparison. The tracked
saved binder used by the Windows CLI is read-only and does not include the
private AI suppression/release experiment. The explicit shared control option
above now implements a separate path, still without native Windows takeover
evidence. See the
[sequence audit](AUTHORITY-CLIENT-PLAYBACK-20261117.md#follow-up-the-first-pose-comparison-happens-after-takeover-begins).
The user has been asked whether to implement a separately verified initial
placement on the isolated fixture or first gather early pose measurements.
Neither behavior nor thresholds have been changed; no native test was repeated.

Current client checkpoint: the Windows fixture CLI now accepts an optional
private `--motion-config` for an existing server stream. It shares the Linux
overlay and one-attempt `ParticipantMotion` lifecycle, including deferred READY
after resume, native Windows UDP-peer ownership checks, source position/velocity
delivery, and confirmed STOP before pause or process exit. It does not configure
the server stream. Binding-only mode does not write positions; playback remains
restricted to the existing recovery fixture at index 1318. No alignment snap,
clock change, server redesign or normal profile changes were made.

Validation: 23 shared-overlay tests passed. The extracting agent reported 32
shared-lifecycle/legacy tests passing (original output not retained), with focused
follow-ups for receipt counting and captured socket ownership. Of 61 Windows
integration tests, 59 initially passed; two failed because a new test request ID
did not match its source sequence. Both passed after correcting that fixture.
Two additional tests passed after fixing the command budget to cover lazy READY
and STOP separately: controller timeout + 2 * motion timeout + 1, at most 300s.
The assembled tests carry actual position/velocity through local TLS/TCP/UDP
and reject a false STOP before pause while still cleaning up. Windows APIs and
X4 remain simulated. Logs and usage are in the
[Windows guide](../tools/dev/AUTHORITY-WINDOWS-FIXTURE-CLIENT.md#optional-motion-diagnostic).
No native game, Wine, Windows, WAN or full-suite run was repeated. A read-only
inspection of the existing isolated offered checkpoint confirmed the two
identity-fixture ships; the identity admission gate remains unchanged.

Next evidence needed is native Windows startup/ABI behavior and successful
paired movement. The failed 88m Linux initial alignment and source/client clock
questions below remain unresolved and await user decisions; do not silently
change either. GPU-free server development stays deferred per the user's
client-first priority. Earlier entries below record the preceding steps.

The Windows fixture CLI now derives registry status from the exact staged
checkpoint before overlay installation or X4 startup. All five XML passes can
pump the load connection on its owner thread; callback failure aborts the join.
Overlay, observed session and final log verification share one status/nonce.
The 15 lifecycle tests passed, as did the assembled local TLS/file/TCP/UDP test
with a synthetic gzip/XML registry. A delayed parser chunk forced a real
keepalive before admission. Windows APIs and X4 remain simulated; no native
Windows, game, full-size save, WAN or full-suite run was made. Logs:
`.local/windows-registry-session-20261118.log` and
`.local/windows-registry-assembled-20261118.log`. At that point motion overlay/IPC
integration was pending; the current optional integration is described above.
The reader change passed 28 focused pump/marker/registry tests, including
propagation across all five passes and unchanged cancellation exceptions:
`.local/registry-inspection-pump-20261118.log`.

Motion profile checks now share lexical path normalization for absolute POSIX,
Windows drive and UNC paths. Case and interior separators remain significant;
relative paths, dot segments, device prefixes and other profiles are rejected.
No movement limits, startup order or clock semantics changed. The focused run
covered 31 tests: eight passed initially, the affected 23 passed after correcting
two outdated test assumptions; the final root-relative-path fix passed its
single helper test. See `.local/windows-motion-paths-20261118.log`. LuaJIT and a
fake native ABI were used; no Windows engine or game was started.

The next Windows prerequisite now shares the saved-registry verifier/status
reader with the existing Linux tools (`authority.registry_evidence` and
`authority.saved_registry`). The verifier function's AST is unchanged; the
status reader has clearer local names. The Windows overlay and observed session
accept optional `registry_status`/`registry_nonce`, reuse the paused load gate
and require its correlated epoch/count receipt before admission. Existing
wrappers preserve their APIs. Focused validation passed 22 core tests plus 48
overlay/parser/session tests, including generated Lua with a simulated engine
and local TCP/UDP with scripted participants. Evidence and limits are in the
[Windows guide](../tools/dev/AUTHORITY-WINDOWS-FIXTURE-CLIENT.md#shared-registry-and-motion-integration).
The CLI orchestration above now uses the reader's optional pump between bounded
chunks. Do not block the connection owner during a live load without pumping.
No native game, Windows, WAN, full-suite or full-size save reinspection was run
for this extraction.

Latest Windows client continuation adds `WindowsMotionPeer`, using fresh IP
Helper UDP owner tables and the existing process owner's held handle/job. It
refuses ambiguous port owners and rechecks process/socket ownership around the
separate IPv4/IPv6 snapshots. This is local sampled ownership, not proof of a
remote UDP endpoint. Fourteen simulated-API tests passed; the process-owner
module passed 15 tests plus one new focused native-handle recheck test. A Zig
0.15.2 x86-64 Windows compile against MinGW headers confirmed the table layout
and API declaration. No native Windows, X4 or full-suite run was made. The
validator now serves the existing motion IPC's `validate_peer` hook in the
optional fixture CLI path. See the
[Windows guide](../tools/dev/AUTHORITY-WINDOWS-FIXTURE-CLIENT.md#shared-registry-and-motion-integration)
for private evidence paths and limitations. No initial alignment, clock basis,
server architecture or normal profile changes were made.

Latest native result: paired native05 reached one confirmed client receipt, then
failed the unchanged 50m alignment bound with a measured separation of
88.08677088848634m. The new diagnostic retained both positions and separate game
times (source 20.7842s, client 21.6727s); these are not simultaneous observations
and do not establish the cause. No continuous paired movement was proven.
Outer cleanup and source preservation passed; a subsequent scan found no X4.
The coordinator's graceful display-release flag and outer observation-valid flag
remain false; this is an overall failure. Details, artifact hashes and the
comparison with the existing LAN replica method are in the
[client report](AUTHORITY-CLIENT-PLAYBACK-20261117.md#paired-native-attempt-05-measured-initial-offset).
No repeat run or initial snap/clock change was made. Native03/04 below are
retained as preceding context.

Client continuation now adds an optional motion consumer to
`ObservedClientSession`, using the existing TCP owner's `apply_motion` hook.
The session checks its log and process/profile guard before and after dispatch;
a late log or controller fault prevents a positive receipt. The caller still
owns motion readiness, peer ownership, STOP and cleanup. The 15-test session
module passed; subsequent focused checks including a new controller-fault
regression passed (final two checks: 0.407s). The tests use real local TCP/UDP
and the real motion IPC adapter with a simulated engine peer. Private output:
`.local/observed-motion-session-20261118.log`. No X4, full-suite, Windows or WAN
test was repeated. The optional Windows fixture integration described above
now uses this hook together with the shared motion lifecycle and Windows peer
validator.

Read-only inspection of native05's offered/staged checkpoint resolved saved
index 1318 to ENH-870 and recorded its saved movement fields. The saved position
is zone-relative and cannot directly explain the live sector-space discrepancy.
Selected results and query bodies are in
`.local/paired-initial-save-evidence-20261118-01/`; see the client report for
the digest and limitations. The initial-alignment question has been presented
with the new measured offset; no answer or implementation is recorded yet.

Client follow-up: `load_observations.py` now extracts the existing ordered
load/marker/pause parser from Linux tooling for use by either client platform.
The existing Linux caller delegates to it; Windows process integration remains
pending. The earlier focused parser/legacy run passed 12 tests. The one-shot
`saved_motion_apply.lua` state machine also has clearer variable names and
layout; its three existing tests passed, and an independent LuaJIT listing
comparison found identical instructions and visible constants after excluding
debug names and source locations. No new X4 run or full-suite run was made.
The user's decisions on a separate initial position alignment and the motion
clock basis are still pending; neither behavior has been changed.

The Windows launcher now resolves Documents through the current-user Known
Folder API rather than assuming `USERPROFILE/Documents`. Four mocked-ABI
tests passed. Static inspection of the pinned Windows X4 image found the same
Documents GUID/API call; the final engine profile path and native Windows
behavior were not tested. See
[the path evidence](WINDOWS-DOCUMENTS-KNOWN-FOLDER-20261118.md).

`ObservedClientSession` now connects a staged client owner, ordered log
observations and local UDP control to the existing participant connection.
Nineteen focused parser/session tests passed in 2.643 seconds, using real local
TCP, file transfer and UDP with simulated X4 responses. They cover fragmented
and late error records, altered logs/offers, disconnects, keepalive and owner
thread constraints. The session checks observations before acknowledging a
local command; an effect already dispatched before a subsequent fault cannot
be undone. Its caller still owns X4/process/profile/log provenance and cleanup.
This bounded diagnostic is not yet connected to a native Windows supervisor.
See [the client barrier contract](../src/authority/CLIENT_LOAD_BARRIER.md).
No new X4, Windows, Internet or full-suite run was made for these changes.

The client-first continuation now includes an opt-in Windows fixture CLI,
`tools/dev/authority_windows_fixture_client.py`, composing the existing TLS,
staging, overlay, process owner and observed session. It uses only a new 45841
profile and new private output containers, and retains artifacts instead of
overwriting or recursively deleting prior runs. The native process is stopped
before connection teardown; uncertain cleanup is an error. Fast idle polls
are paced to avoid spinning on incomplete log lines. Twelve focused lifecycle
tests and five CLI/config tests passed with simulated Windows/X4 edges. The
workspace's nine filesystem-backed tests also passed with Windows commands
and game setup simulated; actual NTFS junctions and ACL inheritance remain
unverified. Initial profile settings are checked once before launch and may
then be rewritten by X4; overlay/save identity checks remain active. The
assembled command has not been run with Windows X4; the server must still
provide a compatible marked identity-fixture checkpoint. See
[the invocation and validation boundary](../tools/dev/AUTHORITY-WINDOWS-FIXTURE-CLIENT.md).

The subsequent assembled client test passed over real local TLS, file transfer,
TCP and UDP using the actual workspace, overlay and observed-session code.
Windows setup/process behavior and X4 remain simulated, and the control peer
is scripted. It validates staging, a correlated claim, one resume receipt and
cleanup; it does not execute the DLL/Lua or prove the real server lifecycle.
The final targeted run was one test in 0.459 seconds. No full-suite or native
game run was repeated. The historical bundled Windows DLL lacks the now-required
`monotonic` API; a separate current-source Windows cross-build passed and its
artifact hash is recorded in [the build record](AUTHORITY-WINDOWS-NETWORK-BUILD-20261118.md).
The client guide now specifies that build instead of the historical DLL.

For visibility work, the earlier LAN
`work/x4-playtest7/extension/x4_lan_lab/ui/identity_game.lua` checks radar contact
for an already-enumerated, bounded actor list. Its `universe_game.lua` scans
ships in a sector; neither establishes all actor IDs visible in the current map
viewport. The current authority player-sector reader likewise reports only a
local sector. Do not substitute sector membership for the user's requested
visibility-based interest policy.

The vanilla map source has since supplied a concrete candidate:
`GetMapRenderedComponents` on the shown `MapMenu` holomap. The new opt-in,
read-only `map_render_observation.lua` captures that raw list without the menu's
selected/targeted/stored-object additions, preserving exact local uint64 IDs.
Its focused offline test passed with real LuaJIT buffers and simulated engine
calls. It has no network or automatic UI hook. A subsequent isolated Linux
native run passed closed/open/closed observation with one raw component and
completed cleanup; see [the native evidence](AUTHORITY-MAP-RENDER-NATIVE-20261118.md).
The follow-up [six-view comparison](AUTHORITY-MAP-VIEW-NATIVE-20261118.md) completed
its observations but did not pass the intended visibility test: player zoom and
restoration matched, while fixture focus and pan did not. Every raw list held
only the player. Server-side ship selection from a reported viewed area has
been proposed to the user; no subscription behavior is implemented or approved.
Actual viewport/radar semantics, ship coverage and Windows remain unproven; see the
[contract and next native check](../src/authority/MAP_RENDER_OBSERVATION.md).

> Client-first continuation, 18 November: server graphics work remains deferred.
> The bounded live-input path and explicit fresh-checkpoint paired playback
> diagnostic are wired through the admitted TCP owner. Native paired attempt 03
> exercised the optimized synchronous guards, reducing source binding from
> 34.062s to 2.787s and initial verification from 6.905s to 1.272s. It still
> reached the source diagnostic deadline during collection after 25.348s: one
> source sample was prevalidated and zero client receipts were confirmed. This
> does not establish TCP transmission or native client refusal. Cleanup,
> Xauthority cleanup and source-pin preservation passed; optimization was
> exercised, but paired movement was not. Native08 remains the latest passing
> client playback, with synthetic host controls. General NPC control, exact AI
> restoration, paired movement, Windows/Internet gameplay and the overall goal
> remain unproven. The offline
> [clock-basis observation](AUTHORITY-MOTION-CLOCK-BASIS-20261118.md) records a
> playback error under synthetic unequal clock rates; the user's decision is pending
> and no protocol change has been made. Start with
> [the current client report](AUTHORITY-CLIENT-PLAYBACK-20261117.md) and
> [the playback guide](../docs/AUTHORITY-CLIENT-PLAYBACK.md). The original handover
> below records the earlier checkpoint, not the current branch tip.

The latest follow-up groups process discovery around each single playback pull,
including network waits, while rereading known identities inside. Extra group
members may be detected only after a client effect; exclusive isolated ownership
is assumed. The focused 26-sample fixture passes, but the changed scope has no X4
result yet. Offline tracing found 3,841 aggregate guards and 611 checkpoint checks
for the complete flow. Its helper/file checks are simulated, so do not treat its
timing as a native performance prediction or restart X4 without accounting for
the remaining nested costs. A further private liveness/full-context separation
has reduced the count to 1,395 aggregate guards, still 611 checkpoint calls.
The updated real TCP/UDP fixture passes with simulated engine edges. Full guards
still surround checkpoint operations; file/registry/log changes during the last
lightweight peer check can be detected only at the next full boundary, after a
dispatch. Initial bind, worker STOP and ordinary callers retain full checks.
Native attempt 04 exercised these changes with unchanged limits. Its first
source pull completed in 1.341s with one confirmed client receipt, then the
observer rejected initial separation greater than 50m. Overall FAILED; no
continuous paired movement or STOP/release was proven. All cleanup and source
integrity checks passed. The source position was not persisted on that error
path; a following offline-tested correction now preserves the bounded initial
comparison before rejecting it. Do not infer the exact separation or its cause
from native04. See the current report before deciding on another native attempt.

## Objective and decisions from the user

The user wants one persistent X4 universe, managed by a central server on the
Linux host's machine while that same person plays locally. A friend on Windows
must connect directly over the Internet, without a VPN. Players must eventually
be able to play in different sectors, fight NPCs and each other, trade, board
ships, and command ships belonging to their shared company and account. Missions,
spacesuits and dropped cargo have lower priority. The universe is to stop and
be saved when the last player leaves, and resume when someone returns. Pausing
for a joining player and distributing a save is acceptable.

The user approved using a complete X4 instance as the initial server, one
high-attention authority per area, transfer of that authority to another local
player or back to the server when appropriate, saved registration references
on isolated experimental saves, and creation of newly observed ships as an
experiment. Only ship positions visible to a client should be sent, and
velocity matters for smooth motion. Intermediate positions can be discarded;
reliable events require separate handling. Discuss important architecture
decisions with the user rather than silently changing direction. Tokens and
repeated native tests are expensive; use focused experiments and existing LAN
work. Code should be readable, with descriptive names. Current work is for
internal testing, not a public release.

The ordinary X4 server instance loads the full universe from its save; it is
not configured to simulate only two sectors. The four registered fixture ships
and two-sector probes are narrow tests, not evidence of full-universe
synchronization. The clients currently also simulate independently. The
overall multiplayer objective remains **unmet**.

## Workspace and safety

Repository: `work/x4-authoritative-server-20261115`, branch
`experiment/authoritative-server-20261115`. The `fork` remote is the user's
`Lith7ium/X4-Online` fork; `origin` is the earlier project. Do not modify
`sources/` in the surrounding ChatGPT project: it is read-only reference
material. Preserve the user's real Steam/X4 profile, game and saves; native
experiments use disposable profiles, owned processes and a private Cage/Xwayland
scope. `.local/` contains sensitive and/or large private test artifacts and is
ignored by Git. Do not commit it or pretend its evidence is portable.

The preceding committed native fixture work is `fee3eadc` and `8b381f21`.
The checkpoint containing this handover is the current branch tip. Inspect
`git status`, the branch and remotes before making further changes.

## Evidence and current limitations

- A native Linux loopback fixture exercised two clients in distinct fixture
  sectors, one leaving and rejoining while the survivor was frozen, followed by
  a checkpoint. The ships were stationary; this did not prove general
  synchronization, Internet, Windows or gameplay. Private results are in
  `.local/private-fixture-player-rejoin-scope-real-20261117-01/`.
- Two independent Linux reloads of the same fixture save gave identical
  positions for the sampled stationary anchors. A separate paused local setter
  moved one registered fixture ship by 10 units with immediate readback. These
  do not establish a universal coordinate frame, persistent physics or
  multiplayer movement.
- New default-off test code implements a real local sample-to-server write path
  and an experimental one-shot client throttle pulse. Offline tests cover the
  separate pieces and a simulated chain. The attempted three-X4 native chain
  **failed**: the client log showed START_INTENT, STARTED and STOPPED for the
  pulse, but the controller did not confirm it, so the server write was not
  dispatched. The error's underlying cause was discarded by the earlier code;
  it might be a deadline, guard or packet issue and is not established. The
  current code records redacted structured failure phases for a future attempt.
  The supervisor reported a control cleanup error; the outer private scope
  confirmed cgroup and Xauthority cleanup and Steam identity was unchanged.
  See `.local/private-fixture-player-write-scope-real-20261117-01/`.
- CPU measurements, conditions and limitations are documented in
  `reports/AUTHORITY-CPU-FIXTURE-20261117.md`. In brief, the single-X4 test
  averaged 218% of a logical CPU; server plus first client averaged about 566%
  combined, plus 94% for the test supervisor. The second measurement is a
  preliminary subset of the failed enclosing run. The experiments differ in
  scene and diagnostic overhead; neither measures FPS or busy combat. This is
  a serious resource concern, not proof the design is unplayable.
- The latest tests and their exact outcome are recorded in the checkpoint note
  below. A previous full suite also had skips and a transient UDP ownership
  failure; a single passing rerun did not make that full suite pass.

## Reuse and next work

Prior LAN work is locally available at `work/x4-playtest7/`. Host-guided trade
code is in `x4lan/economy.py`, `extension/x4_lan_lab/ui/trade_game.lua` and
`extension/x4_lan_lab/md/x4lan_trade.xml`; earlier native checks used small,
fixed fixtures. FIRE2 event and health-fixture code is in `x4lan/coop.py`,
`extension/x4_lan_lab/ui/coop_game.lua`, and `md/x4lan_coop.xml`; an earlier
projectile orientation criterion failed. Fleet-order prototypes are in
`tools/dev/native_gate_player_orders*` in this fork and were mock-tested;
they are not proof of native order acceptance. Treat these as candidates for
adaptation, not as working Windows/Internet gameplay.

Start by reviewing the actual code, recorded evidence and the user's existing
decisions, then discuss major architectural tradeoffs with the user. Investigate
the failed pulse confirmation without repeated full three-X4 runs. A smaller
single-X4 native IPC diagnostic may help, but cannot reproduce the full
server/session guard load. Two unfinished, untested, **not runnable** drafts
are in `.local/authority_fixture_single_throttle_bootstrap_20261117.lua` and
`.local/authority_fixture_single_throttle_scope_runner_20261117.py`; the latter
contains a `__PINNED__` placeholder and has no complete scope/manifest. Review
and complete them before any use. Do not assume pulse STARTED/STOPPED proves
movement, frame equivalence or a successful authoritative write. No retry of
an uncertain pulse may be issued to the same disposable participant.

The user explicitly asked for an Astra handover. This file and the Git
checkpoint prepare that handover; they do not themselves switch the selected
model or prove that Astra has read it.

## Checkpoint validation

The full development check completed with exit code 1: **4,929 tests in
915.305 seconds, one error and 26 refused skips**. In
`test_authority_client_to_server_apply_worker.Worker.test_fourth_real_sample_is_selected`,
the participant peer ownership check failed with `connected IPv4 flow count
differs from one`. The cause is not established. An earlier full-suite run saw a
similar failure in a different test, which then passed individually; that does
not establish the cause or make either full run successful. The skips include
Windows named pipes and MSI, a Windows Zig cross-check, a released lane tool,
and missing optional x4-re/stock-data inputs. Complete private output is in
`.local/check-cpu-throttle-20261117.log` and remains local. The checkpoint is an
experimental work-in-progress, not a passing release candidate.

A later read-only trace review located that error at initial participant HELLO,
before candidate selection or the fourth sample. The retained error did not
distinguish zero matching UDP rows from duplicates. The diagnostic now appends
only that count, without addresses or ports; ten socket-owner tests passed,
including injected zero/two-match cases. This improves future evidence and does
not establish the historical failure's cause or resolve the full-suite result.
