# Experimental local player-sector reader

`lua/player_sector_interest.lua` and `tools/dev/authority_player_sector_interest.xml`
provide an explicitly enabled, read-only, serialized query. They do not
register events or update hooks, open sockets, write saves, or start X4. An
existing exclusive update/event owner must route the one Result event to the
pending request, invoke `tick`, and fail the enclosing session on uncertainty.

`new_x4` takes distinct fresh 32-hex `epoch`, `incarnation` and `nonce`, an
exact private `expected_save_path`, the existing `resolve` module, a timeout,
`guard(incarnation)` and `complete(result)`. `begin()` issues a fresh nonce plus
counter request; an X4 MD result carries the local `player.sector` and macro.
The nonce must be fresh for each owner and process incarnation, and the event
owner must fence responses from previous incarnations.
The X4 adapter independently verifies that the local player container is valid,
its sector ancestor equals that exact local 64-bit reference, and its macro
matches. It rechecks these around the completion callback. It permits changes
only while each locally seen macro and sector reference remain consistently
associated; ambiguous aliases and more than 4096 distinct sectors fault.
The local reference never appears in the completion result.

Completion `{epoch, incarnation, sequence, sector_macro}` is provisional:
the caller must stage it during the callback and only publish it after
`event()` returns true and a fresh session/process guard passes; on any failure
the enclosing owner must discard the staged result and fence the session.
The external process-incarnation guard is a caller assertion, not proof of
PID/socket ownership or checkpoint identity. Guard and FFI/MD samples are not
atomic and report only a point-in-time sector observation. This module does not detect map viewport sectors, establish portable
sector identity across processes, implement subscriptions or expiry, determine
ships in a sector, or transmit any data. It has not run natively in X4.
