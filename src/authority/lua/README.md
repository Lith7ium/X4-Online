# Read-only ship position scanner

This independent, opt-in development component is not loaded by an extension,
launcher, or game by itself. It reads ship positions; it does not suppress AI,
write positions, spawn or remove objects, send network traffic, or install files.

`ship_scan.lua` returns a module with `scan(engine, identities, options)`. The
caller loads it and invokes it only after the game and the identity registry are
ready. On success it returns `{rows = ..., consistency =
'membership_rechecked_non_atomic'}`. On any detected failure it returns `nil,
error` and no partial rows. Each row contains an explicit `id`, `sector`, and a
`pose` of `x,y,z,yaw,pitch,roll`. Positions are sector-relative; angles are the
radians returned by the game getter. It does not export native handles.

`identities.ship(local_ship)` and `identities.sector(local_sector)` are required
and must return nonempty strings no longer than 256 bytes. The caller is
responsible for mapping to identities meaningful on both instances and for
validating the shared save/registry, identity generation and object lifetime.
Converting a local native handle to a string is **not** a portable identity.
Duplicate ship identities fail the scan. This module does not supply a registry,
prove identical sectors, track creation/destruction, or decide authority.

The injectable engine adapter provides `factions(cap)`, `fleet_count(faction)`,
`fleet(faction, cap)`, `key(local_handle)`, `operational(ship)`,
`is_ship(ship)`, `sector(ship)` and `pose(ship)`. Enumeration functions return a
dense Lua array plus a truncation Boolean; a full faction buffer is treated as
ambiguous. `key` is only a process-local key for consistency checks, never a
network ID. `x4_ship_engine.lua` exports `new()` to bind these functions to the
X4 LuaJIT UI C exports. Construction resolves exports and cannot be tested
outside a loaded game process. Its FFI declarations follow the historical
native prototype; a fresh native test on the targeted build is required.

Options: `max_factions` (default 256), `max_ships` (250000), and `max_fleet`
(default `max_ships`). Limits and invalid values fail closed. Counts are checked
before and after each fleet read; after sampling, the module enumerates factions
and ships again and rejects differing membership, changed counts, duplicate
handles, unavailable objects/sectors, non-finite coordinates, and duplicate or
missing portable identities. It checks that a ship remains operational and in
the same sector immediately after its pose is read.

This is a sequential, **non-atomic** census. A same-count replacement or move
that occurs and reverses between reads may go undetected; samples have different
times, faction enumeration semantics and eligibility are not proven exhaustive,
and parent/identity state can change later. A successful result is not proof of
all ships, a simultaneous universe snapshot, cross-instance agreement, network
replication, or in-game synchronization. The calling application must timestamp,
handle lifecycle and missing identities, apply backpressure or batching, and
validate performance in game before treating the data as usable. Five native
attempts reached the scanner but did not yield an accepted scan receipt. The
first failed in fixture-ID conversion, the second in faction enumeration with
the initial buffer, and the third rejected an enumerated object as unavailable
or not a ship. In the fourth, both local instances observed 148 faction entries
and rejected a non-operational object at entry 59 of the first faction's fleet.
This API result does not establish why the object is non-operational, so it is
not silently skipped. The failed attempts do not establish that every faction
or ship was read. A wreck is one possible explanation: an earlier independent
native hot-join test recorded `IsComponentOperational=false` for a saved wreck
(`reports/LOCKSTEP-HOTJOIN-20261101.txt`). That observation does not identify
the object in this scan or prove that all such results are wrecks.

In the fifth run, the independently enrolled fixture position was successfully
read in each of two native Linux instances at tick 30, with matching recorded
pose values for this fixture. The complete run still failed: both fleet scans
again rejected the non-operational entry. This is a bounded read-only API
observation, not position replication, authority or full-world acceptance.

## Disposable Linux fixture integration

The opt-in `--authority-fixture-scan` bundle option includes the scanner and
bindings in the sealed UI overlay. It requires a 12-ship battle snapshot and at
least 30 ticks, disables fixture engagement, and makes one observation at or
after tick 30 on each local instance. `ship_scan.lua` and `x4_ship_engine.lua`
register `X4LAN_AUTHORITY_SHIP_SCAN` and `X4LAN_AUTHORITY_SHIP_ENGINE` for the
X4 UI loader; importing them alone performs no game call. The probe verifies
the disposable profile suffix, uses **test-only, process-local** enumeration
identities, and logs only fixture 1 and its sector. These labels are not
portable IDs and cannot be used for cross-client replication. This adapter is a
diagnostic; it does not integrate with authority transport or apply positions.

The one scan makes two sequential universe fleet enumerations. It fails closed
at 1,024 faction buffer entries, 4,096 ships, or two elapsed seconds, checked
between API calls. A single blocked native API call cannot be preempted by the
Lua deadline. Each instance first reads the enrolled fixture directly, checking operation,
ship class, sector presence, finite pose and unchanged sector, and writes one
bounded `AUTHORITY_FIXTURE_READ` or `AUTHORITY_FIXTURE_ERROR` record. This
fixture read does not depend on a successful fleet scan. It never queries the
position of an unknown fleet object that failed the operational check. The
runner validates this separately under `authority_fixture_evidence`.

The scan then emits one `AUTHORITY_SCAN_FIXTURE` or `AUTHORITY_SCAN_ERROR`
record. If the scan succeeds, `authority_scan_evidence` includes the distance
between its fixture sample and an independent immediate readback. The distance
is an observation, not a position-equality acceptance threshold. A valid fixture
read does not establish fleet coverage or world synchronization. Missing,
malformed, duplicate, or error receipts fail the run independently of the
existing lockstep validation.

A candidate owned fixture snapshot was checked read-only on 15 November 2026.
It has 12 valid saved fixture references; the private test snapshot itself is
not included in this repository.
The Linux executable SHA-256 matched the runner's pin and its ELF dynamic symbol
table included the seven scanner exports. Those static checks do not establish
that the API calls succeed or have the expected runtime behavior. Zig 0.15.2
was found in a separate local toolchain.
Recheck files, installed content, current processes and resource availability
before a run; the earlier worktree is a read-only source for this purpose.

Example commands from the authority worktree, for this machine, after validating
the current environment and snapshot (a fresh bundle/run name is required):

```sh
X4_SNAPSHOT="<path-to-verified-disposable-battle-snapshot>"
X4_ZIG="<path-to-zig-0.15.2>"
X4_GAME="$HOME/.local/share/Steam/steamapps/common/X4 Foundations"
python tools/dev/linux_gate_live.py bundle --zig "$X4_ZIG" --snapshot "$X4_SNAPSHOT" \
  --out .local/authority-scan-01 --preset linux-core --battle \
  --authority-fixture-scan --ticks 60 --stride 60
python .local/authority-scan-01/linux_gate_live.py run --root .local/authority-scan-01 \
  --user "$(id -un)" --game "$X4_GAME" --display "<private-test-display>" \
  --vulkan-icd /usr/share/vulkan/icd.d/radeon_icd.x86_64.json \
  --no-discard --name fixture-scan-01 --preflight
# Only after preflight passes, run the same command without --preflight.
```

The bundle copies the selected snapshot file into its own private output; it
does not mutate the original. The existing runner requires two local instances,
private `HOME`/XDG profiles, disabled autosaves and Workshop synchronization,
read-only game mounts and a hashed executable, and retains logs and cleanup
status in `.local/authority-scan-01/runs/fixture-scan-01/`. Review each client's
`AUTHORITY_SCAN_FIXTURE` or `AUTHORITY_SCAN_ERROR` record and
`run-result.json`: a successful scanner receipt is distinct from the runner's
lockstep verdict, and a failed or incomplete run remains failed. The launcher
preflight also checks current Steam, display, lock and memory requirements.
