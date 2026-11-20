# Review of the external X4 Online audit

20 November 2026. The supplied PDF identifies version 7.6.0 and the experiment
branch but gives no commit hash. This review starts at fork commit
`7d6e0466`. The PDF lists 119 findings, including eight classified as
critical. The table covers those eight. Additional findings below were
selected for their effect on player data, joining and ship movement.

## Critical findings

| PDF | Assessment against the fork | Action or remaining evidence |
| --- | --- | --- |
| C1 Windows cleanup | Confirmed in the legacy launcher. It creates directory junctions to the real Steam installation and DLC. Its recursive cleanup depended on an API added in Python 3.12, although the kit supports 3.10 and 3.11. | Inspect reparse attributes before traversal, reject linked view and profile roots, and remove nested links themselves. Local disposable-directory regressions passed. A Windows CI job exercises real junctions on Python 3.10, 3.11 and 3.12. Its result is still outstanding. [Launcher](../src/lockstep/launcher/game.py) · [Native Windows check](../tools/dev/check_windows_launcher_paths.py) |
| C2 SSH deployment | Confirmed in the administrative lockstep kit installer. Operator arguments and kit metadata reached commands executed with the deployment account's privileges. The multiplayer listener does not call this tool. | Validate the deployment plan, quote remote values, keep credentials private from extraction, and reject links and special files in the kit. Tests cover archive contents and valid SSH aliases, usernames and IPv6 destinations. No server was deployed. [Installer](../tools/deploy_playtest_server.py) |
| C3 Ship identity | X4 component references can change between saves. Missing objects and wrecks also require different treatment. The current experimental format compares bindings within each checkpoint and records separate binding and operational bits per issued index. | Two saves in one pause and a fresh Linux reload agreed for all 10,082 indices. The Windows X4 executable under Proton loaded the same saved roster and matched all four inspection vectors. Roster growth, identity across extended play and normal disconnect/rejoin still need game evidence. [Linux results](../tools/dev/AUTHORITY-REGISTRY-CHECKPOINT.md) · [Windows executable results](AUTHORITY-WINDOWS-ENGINE-LOAD-20261118.md) |
| C4 Movement throughput | Confirmed for the current single-sample source bridge. Both synchronous and latest-mode requests share a timer measured from the last completed pull. The default is 1/60 second. A hypothetical sweep of 10,082 ships would take approximately 168 seconds even before request latency. The active fixture is bounded much more tightly. | The sweep is a calculation, not a measured universe simulation time. Select ships in the player's visible bubble and map view **before** spending a source request on each one. Measure sample age and count for two clients in different sectors before deciding on batching or changing transport. [Source bridge](../src/authority/experimental_source_motion_ipc.py) |
| C5 Checkpoint cost | Confirmed repeated hashing and XML parsing in the join path. The number of passes depends on the operation. We did not measure the PDF's 9–11 passes as a universal cost. | Reuse the marker proof for the same confirmed checkpoint. Each offer still verifies current compressed bytes, manifest and XML. A repeat offer saves the two marker-specific XML passes. A same-length file with changed content is rejected. Total join time, repeated-offer cost and disk I/O still need representative measurements. [Admission](../src/authority/trusted_marker_load_session.py) |
| C6 Scheduler shutdown | Static review supports a race between entering the native scheduler and disarming it. The early restore path can return before admission finishes. | Open. Before another unattended headless experiment, verify cancellation and restoration across an overlapping start and stop. No native failure was induced during this review. [Scheduler](../src/rust/x4mp-agent/src/sched_live.rs) |
| C7 GPU-free operation | An earlier actual X4 run logged 2,274 vertex-buffer errors in about 55 seconds. The no-draw path skips graphics resource maintenance. The precise allocation that failed was not captured. | Stable unattended operation is unverified. This evidence does not measure simulation performance on the proposed rented server. [Native observation](AUTHORITY-NO-GPU-20261117.md) · [Resource-lifetime analysis](AUTHORITY-GRAPHICS-ARENA-20261117.md) |
| C8 Build and test baseline | The Linux workflow lacked an explicit LuaJIT executable dependency and allowed the corresponding gate check to skip. The optimized C queue test also left a retained frame uninitialized. | Install LuaJIT, remove that skip allowance, and initialize the frame. The compiled queue test passed 12 offline groups on local GCC 16.2.1. The audit used GCC 12. A clean hosted CI result is outstanding. [Workflow](../.github/workflows/ci.yml) · [C test](../src/native/engine/linux/test_gate_stock_queue.c) |

## Client and protocol findings

- **M31, preserving old saves.** The legacy launcher previously treated a
  reserved numeric folder as disposable. It now records ownership when
  creating a new profile and refuses to reset an existing unmarked folder.
  Cleanup checks the staged snapshot's identity and content before removing it.
  A user who needs to reuse a reserved number already occupied by an old profile
  can preserve the whole folder in a backup location first. Experimental
  authority profiles created with `prepare_fresh` remain separate.
  [Launcher guide](../docs/LAUNCHER.md) · [Profile code](../src/lockstep/launcher/profile.py)
- **H2, sector changes.** When no player was watching, the bridge updated its
  source observation but left delivery tracking in the previous sector. The next
  valid velocity could then fault the host. The correction advances source
  sequence, clocks and sector even when there is no recipient. It sends no
  packet and creates no peer receipt. Local TCP/UDP tests include a first
  observer in the new sector and a previously informed observer. The latter
  still needs an explicit resynchronization before accepting the new sector.
  [Regression cases](../tests/test_authority_source_motion_selector.py)
- **H3, control channel.** An idle, admitted peer has no pending reply to send.
  The control owner now drops unexpected input in that state. Valid motion
  receipts continue through the owner of their pending exchange.
  [Control owner](../src/authority/experimental_tcp_control.py)
- **H7 and H8, platform assumptions.** The source bridge now uses a timer for
  its pacing wait, which works without sockets on Windows. CPython's binary
  file wrapper already switches Windows descriptors to binary mode. Separate
  POSIX-only server storage code remains. The actual TLS server already set
  a TLS 1.2 floor. Five test fixtures depended on a platform default and now
  use the explicit server context. [CPython FileIO](https://github.com/python/cpython/blob/3.11/Modules/_io/fileio.c#L441-L444) · [TLS setup](../src/authority/experimental_tls_tunnel.py)
- **H1 and H10, Windows startup.** Microsoft's documented ACL syntax includes
  the disputed switch. The new native test runs the actual commands against
  disposable paths. The historical lockstep DLL lacks the authority clock
  API. The authority client already takes a separately built, hash-pinned DLL,
  exercised under Wine and by Windows X4 under Proton. Running the assembled
  client on a Windows OS remains outstanding. [Microsoft icacls reference](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/icacls) · [DLL build and execution](AUTHORITY-WINDOWS-NETWORK-BUILD-20261118.md)
- **H11, Linux client admission.** The native client previously polled a
  disabled keepalive with its default settings. It now polls during loading
  only when configured to do so. Active participant I/O continues normally.
  Download retry policy and the handling of concurrent log appends are
  separate unresolved items. [Client](../tools/dev/authority_client_native.py)

## Validation scope

One integrated local run at `68592b29` passed all 208 tests in 21 affected
modules in 51 seconds on Python 3.13.18 and OpenSSL 3.5.9. This includes
real loopback TCP/UDP and TLS, simulated game observations, checkpoint files
and disposable filesystem tests. The earlier optimized C queue check is
separate. The external auditor used Debian 12 and Python 3.11.2. Hosted
Windows CI, a clean full-suite pass on this revision, and the direct Internet
game session remain outstanding.

After the profile ownership change, 44 targeted launcher tests passed. In
the complementary launcher integration run, 41 of 49 passed on Linux. The
other eight exercise Windows named pipes and were skipped. The added native
Windows test also covers a successful create, unstage and reset, and
preservation of an unmarked profile. Existing downloaded kits retain their
bundled launcher and need a rebuilt kit to pick up these changes.

## Priorities for the playable client

1. Complete server recovery, admission, last disconnect and rejoin with the
   full register. A separate native server attempt stopped at its initial
   registry capture after reaching the load marker and pause. Its generated
   overlay lacked the source registry script. Commit `9826886a` adds that
   script and checks its bytes in a regression test. The corrected initial
   capture still needs a native run.
2. Verify reacquisition of an NPC after it leaves a client's view and crosses
   a sector boundary. Measure the age of visible positions under simultaneous
   cockpit and map observation. Keep player and NPC velocity in that test.
3. Before the Windows Internet test, check receipt logs across partial
   writes and process shutdown (H4), identity checks for small pinned files
   on filesystems with coarse timestamps (H9), and worst-case job packet
   size against the native transport limit (H12). Keep the agreed shared
   company and account. PvP targeting still requires its own gameplay test.
