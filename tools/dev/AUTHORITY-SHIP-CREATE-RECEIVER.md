# Experimental ship-creation receiver

`authority_ship_create_receiver.xml` is an uninstalled, default-off MD experiment.
It directly extends the saved `authority_ship_registry.xml` state. It does not
itself receive network messages, observe server spawns,
reconcile the client's autonomous simulation, or reproduce a complete ship.

A trusted, strictly serial local test driver must initialize the registry and
receiver once with the same fresh epoch before their common checkpoint. On a
client restored from that checkpoint, an external driver may submit `Create`
to screen `X4AuthorityShipCreateReceiver`, waiting for one response before
sending anything else. Input is an MD table with `epoch`, `index`, `macro`,
`sector`, `owner`, `seed`, `x`, `y`, `z`. `macro` is a ship macro ID string,
`sector` a sector macro ID string, `owner` a faction ID string, and `x`, `y`,
`z` are numbers in metres. The receiver resolves the macro and uniquely matching
faction within the local X4 instance. It accepts only the local `player.sector`
when its macro ID matches `sector`; this test restriction does not identify
arbitrary sectors. The driver must validate types, valid ship macro identifiers,
finite coordinates and a bounded integer seed, restrict them to an explicitly
selected test case, and ensure `index` is the next server-issued integer. The
receiver additionally bounds coordinates to +/-10,000,000 m and the seed to
0..2,147,483,647. It checks that a macro exists but cannot yet prove before
creation that every macro is a usable ship macro. Process-local object references
are not portable network values. Untrusted inputs and authentication remain
outside this experiment.

The client must never allocate registry entries independently during this
experiment. The receiver accepts only the next index, refuses gaps and
conflicts, and records the descriptor and bidirectional object binding. On an
explicit refusal it attempts to latch both the receiver and any initialized
registry as faulted; cue failures or silence are not guaranteed to reach this
path. A replay
is acknowledged only if its descriptor and both binding directions match and
the object is still operational. An entry from the common checkpoint cannot be
adopted as a creation receipt. Lost or ambiguous responses, `Refused`, MD
errors, timeout, a pending flag, or any failed readback stop **all** further
registry and checkpoint use in that client. Discard the disposable case and
restart from the known checkpoint; do not blindly retry or save it. There is no
implemented reconciliation or cleanup of possibly created objects. The bounded
diagnostic below deliberately sends one further request after a conflict only
to test refusal, then discards that isolated case; it is not a recovery policy.

The pending flag is set before the in-memory creation call. It is **not** a
crash-durable transaction log: it survives a process crash only if a suitable
checkpoint was actually completed while it was set, which is not established.
This is not an exactly-once guarantee. The deliberately fixed level-1 loadout
and missing pilot, velocity, rotation, hull, cargo, orders and equipment do not
represent a real NPC ship. Even identical descriptors and seeds do not prove
identical objects. Independent NPC creation may produce duplicates; no census
or deduplication is implemented. Direct cross-script cue writes, table-field
persistence, object validity timing, save/load behavior and X4 expression
semantics all require native verification before further integration.

## Bounded native experiment

Build an opt-in harness on the existing isolated
`authority_registry_census_live.py` / marker save-transfer-load infrastructure;
the separate `authority_create_test_live.py` is a local test harness, not a
production network connection. Use disposable profiles and fresh output paths
only. Stop on a reported probe error, missing event,
conflict, unexpected count or timeout. Record engine logs and the complete
checkpoint artifacts rather than relying on a success message alone.

1. Start the designated server with both scripts in a disposable overlay.
   Initialize both with a fresh epoch and empty registry, pause, and save a
   marker-verified common checkpoint. Record epoch, marker, registry last index
   and checkpoint digest; confirm the receiver state is included.
2. After that checkpoint, create one explicitly selected test NPC ship on the
   server, enroll its actual local reference in the registry and capture the
   returned index and supported descriptor. Confirm it is precisely the next
   index. This is controlled creation, not an observed arbitrary game spawn.
3. Load the same checkpoint in one separate Linux client X4 instance, confirm
   its marker and registry epoch/index, then submit the server descriptor IDs
   exactly once to `Create`, which resolves the local MD objects. Record the new local object
   reference, macro, faction, sector, index, both registry directions, all
   descriptor fields and total relevant candidate count before/after. Treat
   inability to measure count or readback as inconclusive, not success.
4. Submit the same request again. Verify the same local object reference and
   unchanged relevant count. This does not observe every transient create action.
   Then change one descriptor field for the same index; require `Refused` and
   demonstrate that a later request is also refused. Do not reuse this faulted
   client or its save. Preserve logs for independent inspection.
5. Only after the basic run is analyzed, separately assess save/reload of the
   binding and fail-closed pending/interrupted cases using fresh isolated
   checkpoints. Observe MD execution order and save contents; do not infer
   crash consistency from a successful uninterrupted run.

Passing this bounded test would show only the tested synthetic scenario on
Linux. It would not prove arbitrary server spawn discovery, complete state,
duplicate-free simulation, cross-sector gameplay, networking or Windows.

## Observed run

On 2026-11-15 an isolated Linux/Linux run completed the bounded test. After the
common checkpoint the server created one fixture ship, registered it as index
1, and the test supervisor forwarded its macro, owner and sector macro over a
local control connection. The fixture's requested coordinates and seed were
forwarded as well; coordinates were not independently read back from the server
ship. The client created and bound one matching fixture at the same index. A
repeat returned the same client-local reference with no net change in the
observed faction/macro count. A conflicting repeat was refused, the register
faulted, and a later request was refused. Each observed count increased from 158
to 159; these counts are not a complete census. Both X4 processes were owned
and stopped. This was not admission, arbitrary spawn discovery, a production
network path, complete state replication, or a Windows/internet test.

Two earlier attempts failed: the first exposed a Lua multi-return conversion
error and an unnormalized object reference in the test driver; the second
reached server enrollment but the fixture's macro event could not be used by
the client driver. The successful run used identifier strings resolved inside
MD. It does not establish that every X4 value can cross the Lua/MD boundary.
