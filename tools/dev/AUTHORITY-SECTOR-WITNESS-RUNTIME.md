# Local census sector witness query

These default-off, read-only MD/Lua test components are not automatically
installed. Import registers no event handler or update loop, starts no process,
mutates no registry and creates no additional long-lived registry consumer. An
exclusive owner supplies a previously validated saved registry epoch, existing
index, expected sector macro, fresh request ID, current private save path,
deadline and process/queue guard. The caller must route the one matching
`X4AuthoritySectorWitnessRuntime.Result` event and monitor late or unexpected
events through cleanup. `start`, `tick`, `response` and `abort` never poll the
job observer or enroll a ship.

The MD cue reads the saved registry's forward and reverse binding, requires an
operational ship with the requested index and sector, excludes docked/stored
ships and requires exactly one `find_sector` result for the requested macro.
It returns the local ship and sector identifiers only to the same X4 process.
A missing, moved, invalid, ambiguous or otherwise unavailable witness fails;
it is not a successful negative or proof that the sector contains no ships.
The UI side correlates nonce, epoch, index and macro, checks pause and unchanged
game time around two guarded local FFI comparisons of that actor's actual sector,
and demands exact `false` from each docking, docking-in-progress and internal
storage getter. Runtime references are parsed as exact local uint64 values; no
handle appears in the returned report.

A pass is a local observation for this witness, not proof that the engine loaded
exact bytes from a save, that saved and runtime handles have a separately proven
identity, that a sector macro is universally unique, or that another process
uses the same coordinate frame. Pause, sector, docking and registry checks are
point observations and are not one atomic snapshot; unobserved state changes can
occur between checks. The caller must retain queue, process, pause, file and
freshness fencing until controlled use or discard. No transport, multiplayer or
Windows result is implied.

Synthetic checks, including a fake native API with an actor ID above 2^53:

```
python3 -m unittest discover -s tests -p test_authority_sector_witness_runtime.py -v
```
