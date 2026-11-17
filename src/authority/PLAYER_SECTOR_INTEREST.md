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
ships in a sector, or transmit any data.

The private recovered-client motion installer also accepts an explicit
`player_sector` pair of fresh incarnation and nonce tokens. When installed,
its existing update owner starts exactly one query while the client is running,
routes the dedicated result event, and emits only the local sector macro after
the reader and local guard complete. A pending query prevents motion STOP;
after completion, STOP closes the reader, while late events still fault the
enclosing owner. The installer protects both overlay files and redacts both
tokens after owned-process cleanup. The default installer path is unchanged.

This is an additive private diagnostic, not a network interest subscription.
The caller must independently generate and fence the
process incarnation, ensure exclusive event ownership and validate the final
log and process lifetime. A log line is provisional if later checks fail;
no PID, shared sector identity, map viewport, high-attention assignment or
native game behavior is established by the offline tests alone.

The recovered-server supervisor provides a separate default-off
`--diagnostic-client-sector` option only with one-client pair delivery. It
binds the installed diagnostic incarnation to the admitted TCP peer using the
existing test-only incarnation fence. A local query starts only after the
matching BOUND was sent; the supervisor accepts a provisional sector only
after its matching TCP receipt. It first arms the private append-only log watch
after a caught-up pre-send read and finally confirms the value only after
client STOP, owned-process exit and final log checks. The output describes a
point-in-time local observation, not process authentication or portable sector
identity. Filesystem and process checks are sampled; the log fence assumes an
exclusive writer and cannot prove exact emission time or exclude an old-byte
rewrite while the file grows.

One isolated Linux loopback run, `.local/authority-client-sector-once-01`,
observed `cluster_14_sector001_macro` on one client after the motion binding.
The diagnostic reached its complete phase and both workers confirmed STOP.
The supervisor's control flow shows that the sector finalization returned before
the subsequent departure save failed registry validation. The original result
file omitted the finalized sector because it was copied only after that save;
the observation was reconstructed from the logs and control flow. Later runs
retain finalized intermediate sector evidence even when departure fails. This
single local observation does not establish shared sector identity, two-player
visibility, a working subscription, or Internet and Windows behavior.

If construction fails after partial listener registration, the listener or
router claim may remain installed. The caller must fence and properly stop the
private process; neither an in-process retry nor rollback is established.
The offline setup-failure tests use a simulated sender, not native UDP.
