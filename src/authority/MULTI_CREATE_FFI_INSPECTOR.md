# Experimental local X4 multi-create inspector

`lua/x4_multi_create_inspector.lua` is an explicitly enabled, read-only X4 FFI
adapter for the separately correlated `X4AuthorityMultiCreateReceiver.Inspect`
response. It does not register an event, install an `onUpdate` handler, start an
X4 instance, create a ship or send an ACK. The exclusive caller must first match
that MD response to the outstanding request ID, index and descriptor and only
then call `inspector:inspect(actor_hex,sector_hex,index,descriptor)`. Successful
return is `(canonical_decimal_actor_id, true)`; any error permanently faults the
inspector. A timeout is checked around callbacks but cannot interrupt them.

For the isolated profile experiment, construct with `new_x4({enabled=true,
md_inspected=true,frame_confirmed=true,expected_save_path=...,guard=...,timeout=...,
position_tolerance=...,resolve=...})`. `expected_save_path` must be the exact
private `/.../45841/save` path; the caller must independently verify isolation,
owned process identity, stable checkpoint and all event/MD script ownership.
`guard()` must return exactly true only while those external conditions hold.
`resolve` supplies the established exact `parse_hex` and `actor_u64` routines
from `tools/dev/authority_registry_resolve_string.lua`. Timeout is at most 30
seconds; the caller chooses a tolerance from 0 to 2 metres.

`md_inspected=true` is the caller's assertion that a fresh MD Inspect checked
both saved registry directions and the descriptor. `frame_confirmed=true` asserts
only that the supplied coordinates use that same *local* sector frame. The FFI
checks that the actor is a valid operational ship, the returned sector is valid,
the actor belongs to that sector, the actor's macro and owner match, it is not
docked/docking/internally stored, and its position matches within tolerance. It
rechecks the binding, properties, paused state and unchanged local game time
around readback. Both hex identities are converted through exact uint64 values;
a Lua number at or above 2^53 is refused. The inspector does not itself read
MD registry tables, verify a sector macro independently of the correlated MD
response, establish cross-process frame equivalence, verify complete ship state,
or prevent autonomous client ship creation.

`tests/test_authority_multi_create_inspector.py` compiles a disposable fake C ABI
and drives the actual LuaJIT FFI binding, including the maximum uint64 actor and
negative tests for process/paused state, actor/sector binding, owner, position,
clock, unsafe numeric IDs, callback mutation and reentrancy. This is not an X4
run or proof of the native symbols' semantics. The module remains default-off;
no production client, Windows, Internet or shared-world validation is implied.
