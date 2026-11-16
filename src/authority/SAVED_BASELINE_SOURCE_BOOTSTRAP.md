# Experimental local saved-baseline source bootstrap

`lua/saved_baseline_source_bootstrap.lua` resolves one selected saved-registry
index at a time using the already installed, read-only
`X4AuthorityJobDescriptorProbe` MD screen. It does not modify registry or game
state, create a queue receipt, install an event hook, or send network traffic.
The existing owner supplies epoch, saved baseline bound, timeout, guard,
`baseline_guard(epoch, baseline)`, fresh nonce and a local completion callback.

Call `begin(index)` and route the one correlated
`X4AuthorityJobDescriptorProbe.Result` to `event`; call `tick` while waiting.
The request ID uses the first 16 hex digits of the nonce and a local counter.
The owner must ensure that prefix is fresh across all descriptor request
streams and process/load incarnations and fence stale events. The event owner
must route job, motion and bootstrap requests by their outstanding IDs rather
than register competing readers. Unavailable, stale, wrong index or sector,
docking, pause, timeout, guard failure or uncertain callback faults this
bootstrap. No outcome establishes destruction.

On a valid MD response the X4 factory parses exact local 64-bit actor/sector
references and checks roundtrip conversions, operational class, current sector,
macro and dock/docking/storage state with local FFI and game APIs. It calls
`complete(index, actor, sector_macro)` with a **process-local** actor reference;
it must never be sent over IPC/network. Completion is provisional until `event`
returns true and its post-callback guards and local checks pass. A caller must
stage the candidate locally and only register it with the saved-baseline
sampler after successful return, under its own matching guard.

The caller's baseline guard is an assertion, not proof of checkpoint bytes,
loaded save, cross-process identity, sector-frame equivalence, or freshness of
the saved bound. The owner must establish and fence those separately. This
module neither enumerates the whole universe nor connects a session, transport,
interest subscription or existing client. Its focused tests simulate MD and
X4 ABI calls; there has been no native bootstrap run.
