# X4 authoritative multiplayer: handover for Astra 6.2

The [Neon handover](HANDOVER-NEON-20261120.md) records the later successful
two-client sequential rejoin and the current client development branch.

This brief records the paused handover on 20 November 2026. Development resumed
afterward. The [checkpoint guide](../tools/dev/AUTHORITY-REGISTRY-CHECKPOINT.md)
records the subsequent Linux two-save and reload result. The
[Windows load report](AUTHORITY-WINDOWS-ENGINE-LOAD-20261118.md) covers the
full-register client experiment. The [server guide](../tools/dev/AUTHORITY-RECOVERED-LOOPBACK-SERVER.md)
describes how the supervisor creates its first format-3 checkpoint and recovers one.
The shared Windows/Linux Internet gameplay goal remains open.

At the time of the handover the goal was paused.
No model switch is performed by this document. Read this brief first; the older
[handover](HANDOVER-ASTRA-20261117.md) is a chronological archive with superseded
next steps and historical statements that the goal was active.

## Starting state

- Repository: `work/x4-authoritative-server-20261115` within the X4 Multiplayer
  project. Branch: `experiment/authoritative-server-20261115`.
- Fork: `https://github.com/Lith7ium/X4-Online.git` (`fork`). The original
  `Unofficially-Online/X4-Online` remote is `origin`; leave its main branch alone.
- Last implementation commit: `25783512`. Last pause checkpoint before this
  documentation: `c799909fc5493c2638c01847f74e8100d620d682`.
  Local HEAD and the fork branch matched, with a clean worktree, before this edit.
- Goal status was freshly checked as `paused`. A local process-name check found
  no X4 process. No game, code test or remote laptop session was started for this
  handover. This does not establish the laptop's current state.
- First action after the model switch: read this brief and report readiness.
  Resume development only after the user requests it.

## User objective and accepted constraints

The Linux host must play while hosting a central persistent universe. A Windows
friend connects directly over the Internet, without a VPN. Players must be able
to occupy different sectors, fight together and against each other, attack NPCs,
trade, board ships and command their shared company's ships. All players initially
share one faction and account. Missions, spacesuits and dropped cargo are later
work. The world runs while someone is present; the last departure pauses and saves
it. Pausing to save, transfer and load a common checkpoint during admission is
acceptable. This is not an MMO.

Keep the conversation German, and code/documentation/UI English. Tokens and
repeated tests are expensive; use narrow investigations and retained evidence.
The user permits simpler subagents, insists on readable code and descriptive
names, and wants important architecture decisions discussed before implementation.
The current work is internal experimentation, not a public release.

Previously approved directions, not claims of completion:

- Start with one full X4 server instance. A designated client handles a local
  high-attention area; another present client or the server takes over on departure.
  The user's whole-sector delegation suggestion has not become a validated design.
- Send motion where the client actually observes it, including viewed map areas,
  rather than continually broadcasting every ship's position. Include velocity;
  coalesce stale motion separately from reliable acknowledged lifecycle events.
- Experiment with persistent registry references, a saved checkpoint marker,
  ship creation without a pause, and separately acknowledged creation events.
  Persistent lifetime numbers were approved for exploration, but are not complete.
- Missing objects retain identities; absence alone is not destruction. Separate
  object binding from operational eligibility, so wrecks retain valid bindings
  but cannot receive motion or commands. Do not recycle or silently rebind IDs.
- Direct TLS with checked server fingerprint and a shared access key is approved.
- Playback uses a monotonic capture time in addition to game time. Two-stage
  entry prepares the replica, then aligns once to a fresh position/rate sample.
- A bounded diagnostic mode may cache expensive process/socket/save checks for
  at most 250 ms, with full checks at lifecycle boundaries. This is optional test
  policy, not a blanket relaxation for production.
- GPU-free Linux using internal graphics libraries is approved as an experiment,
  but the user subsequently prioritized clients while seeking a real test server.
  Do not restart the graphics work as the default next task.

## Evidence that matters now

1. **One moving ship, two Linux X4 processes:** native04 at `5221187a` completed
   prepared startup, playback and STOP. There were 26 source samples, 14 consumed
   packets and 436 readbacks; final error was 0.002808222 m with a drained, certain
   writer. The unchanged 50 m correction and 0.75 s continuity limits held.
   **The overall test failed afterward**, during registry validation of the save.
   This is telemetry for one fixture, not visual smoothness or playable co-op.
2. **Full issued register, isolated save/reload:** native03 at `af246556` captured
   and freshly reloaded all 10,082 issued indices in 158 batches. All saved/fresh
   binding and operational bits matched: 10,075 bound, seven missing, 10,019
   operational. The 56 bound non-operational objects matched saved wrecks, including
   index 59. `isrealclass.ship` preserves the ship type of a wreck; `isclass.ship`
   did not. This passes the representation/save/reload experiment, not admission.
3. **Repeated checkpoint integration:** implemented at `25783512`, default-off;
   focused structural, Lua/simulated-bridge, saved-reader and schema checks passed.
   No native repeated-capture/save/reload run has occurred with this code.

The seven missing indices are 576–579, 664, 671 and 672. On resave their references
collapse to `[0x0]`; the reverse table then has one null key rather than seven.
The snapshot therefore carries binding state separately from the source maps.
Operational bits are observations, never permission for a later runtime write.
Runtime eligibility must still be checked.

The motion experiment published but did not confirm its candidate:
`CURRENT` was `checkpoint-69e674a31a4645b2bd4b9f15b31e9365`, while `CONFIRMED`
remained `checkpoint-d36e035c0756499e8551512c3b37720b`. These are historical
recorded pointers; recheck them before use. The later diagnostic save was not
published or confirmed. Do not promote either candidate merely because a focused
diagnostic passed.

See [motion and registry evidence](AUTHORITY-MOTION-CLOCK-BASIS-20261118.md),
especially the native04 and full-register format-3 sections. The full register
means all issued IDs, not independently proven coverage of every universe object.
There is still no demonstrated real Windows/Linux Internet session, independent
multi-sector gameplay, shared combat/trade/boarding, general high-attention
handover, or complete departure/reconnect flow. Clients still simulate locally.

## Current code and immediate blocker

[Checkpoint integration guide](../tools/dev/AUTHORITY-REGISTRY-CHECKPOINT.md):

- `tools/dev/authority_registry_availability_snapshot.xml` / `.lua`: `BeginNext`
  requires the previous complete, sealed, nonfaulted run and unchanged epoch/count.
  It preserves prior maps during capture, rejects actor replacement and missing-to-
  bound transitions, permits bound-to-missing without inferring destruction, and
  removes temporary maps at seal. Failed partial captures require recovery.
- `src/authority/lua/registry_checkpoint_gate.lua`: full initial inspection before
  readiness; fresh full capture before each new marker; pause/game-time, deadline,
  callback/reentry and marker-reuse checks. It does not itself save or resume.
- `tools/dev/authority_registry_checkpoint_install.py`: optional integration in a
  disposable recovery bridge. Initial inspection precedes readiness/activation;
  capture precedes marker storage; the existing marker receipt precedes saving.
- `src/authority/registry_availability_evidence.py`: optional
  `verify_source_registry=True` cross-checks the snapshot and source registry in
  the same three streaming passes. It passed offline on the retained native03 save.

**The main recovered server CLI, saved verification and client admission paths
do not yet consume this integration.** Relevant existing paths are
`src/authority/saved_registry.py` and
`tools/dev/authority_recovered_loopback_server.py`. Keep their acceptance strict
until the new evidence is integrated and tested. Issued-count growth is still open.

Private preparation in `.local/registry-checkpoint-repeat-owner-20261120/` is
**unfinished and not ready to launch**. Its `native_adapter.lua` defines a pause
guard but omits `guard=guard` from the checkpoint gate constructor. Request IDs
start at 2 after pause ID 1, and the runner now checks initial Inspect rows, but
these edits are untested. No syntax/fake-event checks or reviewed manifest were
completed. Review the entire launcher, runner, adapter, input/dependency pins and
cleanup before use; fixing the known omission is not sufficient by itself.

After explicit resumption, the proposed small next step is to finish and verify
that harness offline. Only then consider one changed native experiment: inspect
the retained input, capture/save 009, capture/save 010 in the same paused process,
independently verify both saves/markers/source registry, and inspect 010 in a fresh
process. It uses the gate plus the two-save controller, **not** the generated UDP
recovery bridge. It cannot prove full reconnect or a live bound-to-missing event.
Integration with actual server/client checkpoint verification and admission is
the following milestone. Do not repeat the successful single-capture experiment.

## Retained artifacts and validation limits

All paths below are local, ignored by Git and not portable with a checkout alone:

- Motion: `.local/private-paired-capture-native-20261120-04/`.
- Full registry: `.local/registry-availability-full-native-20261120-03/`, with
  manifest `.local/registry-availability-full-reviewed-20261120-03.json`.
- Full-registry output: `capture/case/home/.config/EgoSoft/X4/45841/save/save_009.xml.gz`
  under that run. The repeat harness has a read-only copy named
  `input-save_008.xml.gz`. Both refer to the retained 27,095,551-byte save with
  SHA256 `b8dd4f45c4cdcb75e5adbf17e977d3251e8c9340ac6cd1bfebe6e1d7fda97377`.
  The copy and its hash were freshly checked for this handover.
- Snapshot marker/run ID: `87d71f76771a398acf7236bf19fc2cec`.
- Laptop access/startup evidence: `.local/fedora-laptop-access/`. SSH and an X4
  menu-only startup were previously demonstrated; no two-host world test was.
  Keep credentials private. Shared Steam account/license constraints remain to
  be resolved before concurrent play; do not disable SELinux or buy a license.

The latest implementation checks recorded seven MD structural tests, the extended
snapshot Lua-owner test, 11 saved-reader tests, three gate/installer Python tests,
and final MD XSD validation passing. They were not rerun for this documentation.
The latest recorded broad check at `a3296cf1` ran 5,263 methods and failed with
one failure, three errors and 56 skips. Four stale-fixture findings were corrected
and passed targeted reruns; 30 skipped methods passed with existing prerequisites
selected. The remaining 26 require Windows or missing inputs. This is still not a
passing full suite; see the full-check section of the motion report. Older 4,929-
method results in the archived handover are not the latest broad result.

## Architecture and resource assessment to carry forward

The ordinary server instance loads the full universe, not just test sectors.
Fixture selection limits observation, not universe simulation. The clients also
run their own X4 simulations; delegation, suppression and reconciliation are
not complete, so the current code is not a validated simulation offload design.

[GPU-free evidence](AUTHORITY-NO-GPU-20261117.md): a bounded full-gamestart Linux
run without GPU device access recorded 1,217 consecutive scheduler steps with no
render decisions. In a roughly 55-second window it used 83.60% of one logical CPU
at configured 20 Hz and advanced game time near real time. RSS was about 7.5 GiB.
It still initialized software Vulkan, a virtual display and graphics resources,
and emitted 2,274 vertex-buffer errors: stable-server acceptance failed. Never
present its raw `success=true` as a stable headless-server pass. The staging-arena
lifetime explanation remains a hypothesis, not a safe fix.

[Older rendered fixture measurements](AUTHORITY-CPU-FIXTURE-20261117.md) observed
218.2% CPU for one X4 and about 566% combined for server plus one client, with
substantial supervisor cost and different scenes. These are not controlled
comparisons with the GPU-free run, nor busy-universe/FPS benchmarks. They neither
confirm nor refute Silver's report about an unspecified Milan-class server CPU.
Real rented-server capacity remains untested; the user is seeking test hardware.

## Working boundaries and references

Read repository `AGENTS.md`; read `docs/LAUNCHER.md` before any native launch.
Never alter the normal X4 profile, saves, settings or installed game files.
Use disposable profile 45841, owned process/display scopes and exact build pins.
The surrounding project's `sources/` is read-only. Do not commit `.local/` or
credentials. `.local/` preparations need review even if a previous agent wrote them.

Prior LAN work is at sibling `work/x4-playtest7/`, including `x4lan/economy.py`,
`x4lan/coop.py`, trade/co-op Lua and MD. Fleet-order prototypes are already in this
fork. Reuse these where appropriate, but distinguish legacy LAN observations from
proof on this architecture. Avoid rebuilding solved transport or movement pieces
without inspecting them first.

For the full historical trail use [the archived handover](HANDOVER-ASTRA-20261117.md).
For immediate implementation details use the checkpoint guide and motion report
linked above. No new architecture decision or native test was made in preparing
this handover.
