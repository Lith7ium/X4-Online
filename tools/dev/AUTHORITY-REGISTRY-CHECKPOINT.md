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

The supervisor must verify the new snapshot against the requested marker and
the complete capture receipts before confirming a checkpoint. Saved operational
bits grant no runtime write permission. The current integration keeps issued
count fixed; registration growth, recovery admission, client installation and
the complete disconnect/rejoin flow still need integration and native evidence.

Targeted tests cover the full 10,082-entry owner protocol, repeated captures,
correlation failures, timeouts and callback failures. The generated bridge test
uses the real Lua control owners with a simulated engine and MD responses; it
covers two saves separated by resume/pause, unavailable transitions, stale
markers, a mismatched reload and pause loss. These tests are not native gameplay
evidence. See the latest handover for native observations.
