# X4 multiplayer: handover for Astra

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
test was repeated. This hook is not yet wired into the Windows fixture CLI;
its next required pieces are the motion overlay/lifecycle and a Windows peer
validator, as described in the updated Windows client guide.

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
