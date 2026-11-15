# Experimental local X4 control bridge

`LocalControlBridge` implements the blocking engine interface consumed by
`WorldCoordinator` using the asynchronous Lua `control_state` receipts. The
UI entrypoint is `tools/dev/authority_world_bridge_probe.lua`. Nothing installs,
starts, or registers it by default. It is an experiment for one exclusively
controlled X4 process, not a multiplayer protocol or a safe general-purpose
profile controller.

For an isolated run, create the private X4 case, namespace, empty 45841 profile
and fenced process using the existing `linux_snapshot_capture` isolation
mechanism. Install the Lua state, X4 binding, bridge and probe in that disposable
case's UI loader in that order; compile its `src/native/net.c` module into that
case. Configure `authority_world_bridge=true`, `test_profile="45841"`, a
loopback UDP port, and fresh independent 32-character lowercase hexadecimal
`authority_control_lease` and `authority_world_epoch`. The UI verifies the
save folder suffix and checks slot `save_009` is empty before enrollment.
The launcher must independently verify profile isolation and exclusive control;
a folder name or an empty slot alone is not proof. Do not mount normal saves
writable or allow other scripts, UI actions, autosaves or clients to save.

Bind an IPv4 UDP socket to `127.0.0.1` before X4 starts. Enroll the source
address of a matching `HELLO|lease|epoch` from the owned isolated process, then
construct `LocalControlBridge(enabled=True, sock=..., peer=..., lease=...,
world_epoch=..., profile=..., store=..., verify_checkpoint=...)`. The verifier
may be `read_cycle_evidence` from `tools/dev/authority_control_cycle_evidence.py`;
it independently checks the full published checkpoint and its exact per-request
save title. Pass that adapter to `WorldCoordinator` and serialize all its calls.
The UI retains the slot until a verified checkpoint has been published and the
Lua controller explicitly acknowledges `confirm_save`. Load confirmation and
player authentication are still external and are not established by this bridge.

Packets are local experimental control messages protected by a per-run secret,
not a security boundary against a same-user process. There are no retries. Loss,
timeout, malformed receipts, verification failure, and process failure leave the
engine state uncertain and fault the adapter. Do not call `SessionCoordinator.retry`
until the old process and all its commands have actually been fenced. A
checkpoint can remain published after a later confirmation failure; it is not
then a confirmed session baseline. Keep a new epoch and lease for every restart.

`tests/test_authority_world_bridge.py` exercises the UI entrypoint, real native
UDP library and controller with Lua engine doubles across three save cycles, and
publication failure. It does not launch X4 or demonstrate native gameplay,
save loading, player synchronization or isolation by itself. The existing
`authority_reuse_live.py` is a separate three-cycle native experiment and does
not exercise this bridge.

`tools/dev/authority_world_bridge_live.py --game GAME_DIR --out NEW_OUTPUT_DIR
--display :0` prepares and runs that disposable case using the existing
capture isolation, installs the opt-in UI bridge and executes the real
`WorldCoordinator` through two pause/save/resume cycles and a final pause/save
when the last simulated client departs. Its client load confirmations and its
participant pause/resume adapter are fake; there are no client processes. The
load confirmations are explicitly marked FAKE in `result.json`. It is never invoked
on import. `--help` lists its parameters.

On 2026-11-15, one isolated Linux X4 run completed this lifecycle: the game
saved on each simulated join, remained running after the first simulated
departure, then published a distinct checkpoint and remained paused after the
last departure. The owned process was stopped afterwards and Steam identity was
unchanged. The two load confirmations were deliberately faked; no client
download, actual client load, Windows client, internet connection, gameplay or
restart from the last-departure checkpoint was exercised in this run. A
separate native checkpoint-reload experiment is described in
[`AUTHORITY-REPEATED-CHECKPOINT.md`](../../docs/AUTHORITY-REPEATED-CHECKPOINT.md).
The participant pause/resume requirement was added after that native run and
has been checked with doubles, not re-run against X4.
