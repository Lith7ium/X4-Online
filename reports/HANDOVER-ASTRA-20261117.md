# X4 multiplayer: handover for Astra

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
No native retry has yet exercised these two changes. See the current report for
the real-helper measurement and precise limits.

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
