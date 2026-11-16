# Experimental local replica motion binding

`lua/replica_motion_binding.lua` and `tools/dev/authority_replica_motion_bind.xml`
are a default-off read-only local X4 binding experiment. They do not install an
extension, register a handler, pump a socket or apply position/velocity. The
existing exclusive onUpdate/event owner must route
`X4AuthorityReplicaMotionBind.Result` to one adapter and call `tick()`.

Construct `new_x4` for one already confirmed replica with explicit `epoch`,
`generation`, `index`, `sector_macro`, fresh 32-hex `nonce`, `timeout`,
`max_age`, `expected_save_path`, `resolve=X4LAN_RESOLVE_STRING`, a process
`guard`, and `complete`. Call `begin(sample, arrival)` with the validated
portable snapshot and its local monotonic receipt time, then route the one
correlated MD reply to `event`. Completion contains only epoch, generation,
index, sequence and sector macro; it is provisional until `event` returns true.
The caller must not treat an earlier completion as accepted if event fails.
There are no local actor, sector or zone handles in the completion result.

The MD read checks the stored MultiCreate replica receipt and the saved ship
registry's epoch and both lookup directions, an operational undocked ship and a
uniquely resolved local sector with the requested macro. The X4 FFI adapter
independently parses returned hex references exactly, checks conversion
roundtrips, component lifetime/class, sector context, zone ancestor and
not-docked/not-docking/not-stored state before and after local reads. A new
probe is required for every observation; stale input or sequence, a failed or
late response, lost actor, changed local actor/sector/zone, pause or failed
context fences the instance. The caller must fence delayed old events across
process, session and load changes and generate a cryptographically fresh full nonce for each owner/process/load
incarnation. Request IDs include the entire nonce, local registry index and
per-track counter; the module cannot prove freshness across processes. The arrival time
is a caller assertion; it does not establish source sample age, clock
synchronization or network latency.

MD and FFI checks are separate, non-atomic observations. A stable zone
ancestor does not prove the direct parent or absence of moving-parent effects;
sector macro uniqueness locally does not prove the same sector or coordinate
frame across processes. This only covers entries created and receipted by the
MultiCreate receiver; baseline ships and rejoin semantics need separate work.
The synchronous TCP motion consumer is not connected to this asynchronous
binding. In particular, this module is not proof of a working motion receiver,
velocity, smoothing, actor destruction propagation or gameplay.

`python3 -m unittest discover -s tests -p 'test_authority_replica_motion_binding.py' -v`
runs only Lua and fake X4 ABI tests; it does not start X4. The separate XML
was checked against the checksum-verified X4 `08.cat` MD schema, which does
not prove runtime behavior or format of the new MD response.
