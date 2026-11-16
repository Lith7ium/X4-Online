# Experimental saved-baseline motion binding

`lua/saved_baseline_motion_binding.lua` is a separate, opt-in, read-only local
binding for a selected index in an externally identified saved registry. It
does not create an object, change the registry, install an update hook, send a
network message, or authorize pose/velocity writes. The normal
`X4AuthorityReplicaMotionBind` screen still requires its MultiCreate receipt;
this module uses the separate `X4AuthoritySavedBaselineMotionBind` screen.

The caller supplies a frozen epoch, generation, index, saved-baseline upper
bound, local sector macro and a fresh 128-bit nonce, plus the existing
`replica_motion_binding` and `X4LAN_RESOLVE_STRING` modules. The caller owns
the one update loop and routes the separate
`X4AuthoritySavedBaselineMotionBind.Result` event to `event`. `begin`, `event`,
`tick`, `state` and `close` retain the existing binding's sequencing, timeout,
callback and local FFI checks. Completion is provisional until `event`
returns true. It contains no local actor, sector or zone handle.

The caller's `saved_baseline_guard(epoch, baseline)` is required before and
after asynchronous local work. It is only a caller assertion: the module
does not itself hash a checkpoint, prove which save X4 loaded, prove two
processes loaded the same world, or authenticate the baseline bound. An outer
owner must establish those facts using its own load/process/checkpoint fences,
including exclusive event routing and delayed-event fencing. Successful local
completion explicitly reports `checkpoint_identity_proven=false` and
`cross_process_identity_proven=false`; it cannot be used as a MultiCreate
receipt. Actor lifetime, context and guard samples are non-atomic. Index/epoch
or equal sector macro alone do not prove cross-process actor identity or frame
equivalence. Unavailable, stale, changed sector/zone, docked, missing or
uncertain bindings fail closed; no destruction or sector transition is inferred.

The MD screen checks the local registry epoch, baseline/index bounds, both
registry directions, operational undocked ship, unique sector-macro match and
local ship-sector membership. The shared X4 FFI path independently verifies
the returned local actor, sector and zone and their identity conversions.
The outer owner must generate a new nonce and fence old events on every
process/load incarnation. There is no all-universe inventory, actual motion
stream, client admission, Windows or Internet gameplay claim.

`python3 -m unittest tests.test_authority_saved_baseline_motion_binding
tests.test_authority_replica_motion_binding -v` uses a fake local X4 ABI and
static XML inspection. No native baseline bind is established by these tests.
The local X4 schema was available, but its compilation did not finish within
the bounded 60-second attempt; schema validation is pending.
