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

The experimental source session now has a default-off **local** adapter. An
owner that supplies the bootstrap module and a trusted
`authority_source_saved_baseline` configuration table can pass `enabled=true`,
a fresh `nonce`, a `guard(epoch, baseline)`, and a nonblocking `next_index()`
that returns one selected index or nil. The session freezes these functions and
baseline values, requires a distinct descriptor nonce prefix, routes replies by
outstanding request ID and stages the callback. Only after `event` succeeds and
the baseline guard passes again does the next session update register that
local actor with the existing saved-baseline sampler. A failure fences the
session; the adapter does not retry or invent a job confirmation. Candidates,
the true checkpoint identity and its ongoing fence remain caller duties. The
private installer does not configure this route. It does not connect the
registered index to the TCP tracker or implement player/map interest selection.
The coupled offline test uses the real session, bootstrap and sampler with a
fake X4 ABI and simulated MD; no native game behavior is established.
