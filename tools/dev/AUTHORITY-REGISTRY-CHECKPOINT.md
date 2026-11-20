# Registry capture before checkpoint saves

This opt-in integration is for isolated internal recovery experiments. It does
not enable multiplayer admission or replace the existing strict registry checks
in `authority_recovered_loopback_server.py`.

`authority_registry_checkpoint_install.install(case, nonce, evidence)` adds the
registry gate to a fresh overlay produced by
`authority_recovery_bridge_live.install_probe()`. The caller must first verify
the input save, its marker and its format-3 snapshot. Use
`registry_availability_evidence.verify(..., verify_source_registry=True)` to
cross-check the snapshot against the source registry in the same saved bytes.
The installer rejects conflicting registry-status owners and validates its
hooks before changing the disposable overlay.

The generated bridge performs these operations:

1. After the existing load/marker/pause checks, inspect every registered index.
   Saved and fresh binding and operational vectors must match the independently
   read input snapshot before `RECOVERY_READY` can be sent.
2. On each save request, use its fresh checkpoint marker as the next snapshot
   run ID. `BeginNext` requires the immediately preceding sealed run, identical
   epoch and issued count, and a complete, nonfaulted prior capture.
3. Capture all indices in batches of at most 64 while the pause and game time
   remain stable. Retain valid bindings, allow a bound object to become missing,
   and reject missing-to-bound transitions or replacement objects. Operational
   observations may change independently. The source registry stays read-only.
4. Only after successful full capture and seal, store that same marker. The
   existing bridge waits for its marker receipt before issuing the native save;
   it still requires independent saved-file verification before reuse/resume.

Prior maps remain available during capture for continuity checks and are removed
at seal. Completed snapshots retain the format-3 saved contract. Failed partial
captures cannot be reset or used for saving; recovery requires a previously
verified checkpoint. The gate rejects marker reuse within its lifetime and
limits each full operation to the configured timeout (110 seconds in this
installer). It never initiates saving, loading or resuming itself.

The [recovered supervisor](AUTHORITY-RECOVERED-LOOPBACK-SERVER.md) can now
verify the saved snapshot against the requested marker and the complete
capture receipts before confirming a checkpoint. The [Windows fixture
client](AUTHORITY-WINDOWS-FIXTURE-CLIENT.md) can require a matching full
inspection before claiming admission. Commands still require a fresh runtime
eligibility check. Issued count stays fixed during a capture. Registration
growth and a complete Windows/Linux disconnect and rejoin still need evidence.

Targeted tests cover the full 10,082-entry owner protocol, repeated captures,
correlation failures, timeouts and callback failures. The generated bridge test
uses the real Lua control owners with a simulated engine and MD responses; it
covers two saves separated by resume/pause, unavailable transitions, stale
markers, a mismatched reload and pause loss. These tests are not native gameplay
evidence. See the latest handover for native observations.

### Native repeated-save result, 20 November 2026

At `df5d1761`, a disposable Linux X4 instance loaded the retained format-3
checkpoint, paused and inspected all 10,082 entries. It took a fresh registry
snapshot immediately before each of two saves in that same pause. Each save
carried its own marker. The supervisor verified both compressed saves against
their respective native receipts, markers and source registries. A second X4
process then loaded save 010 and inspected all entries. Saved and fresh binding
and operational observations agreed. Both processes exited with verified cleanup.

| Slot | Checkpoint marker | Compressed SHA-256 |
| --- | --- | --- |
| 009 | `413da4c401c69c78d5ba6374863f9ddc` | `b34b8446866e4b71d4d74661bf2893f6deef7354855bc1801ccb8c87ebc20841` |
| 010 | `13231d6de5d086e2eb4dce8121d9299f` | `b051ff4ccee778ca7cb96e3cc7bcadfa4ba53c7e920e7814ac72db38aa304d36` |

Each observation found 10,075 bound objects, including 10,019 operational
ships. The same seven indices were missing in both saves and the reload.
The test used the actual checkpoint gate and a two-slot save controller.
The world stayed paused between saves. Reconnecting a player through the
recovery server and capturing registry changes during play need separate tests.

Private evidence lives in `.local/registry-checkpoint-repeat-native-20261120-01/`.
The outer `result.json` confirms success, source pins, process/display cleanup
and Steam identity. The detailed evidence SHA-256 is
`8a2edd9a29d0201266b0bbcc1d1fa0ad6d1a9202c404691e1781115e9cc22fc6`.
