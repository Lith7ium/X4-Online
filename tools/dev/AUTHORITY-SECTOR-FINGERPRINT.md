# Two-profile saved ship and sector fingerprint diagnostic

This is a read-only experiment, not a network identity mechanism. Two distinct,
fresh disposable Linux profiles are started **sequentially** from the same
fixed archived checkpoint and seed. Profile 2 starts only after profile 1 has
succeeded and its owned-process cleanup is confirmed. Neither profile saves,
creates ships, changes orders, moves objects, admits a client or modifies the
source archive. A failure in either profile makes the comparison inconclusive.

Before starting X4, the archived pointer, compressed digest, marker, registry
epoch and two saved fixture/registry/sector relationships are checked. An
independent streaming parser then reads the two ships' saved `code` and `macro`
and their actual ancestor sectors' `code` and `macro`. It rejects ambiguous
fixture codes anywhere among saved universe components and duplicate sector
macros. It does not promote saved component IDs to network identity.

Each profile loads the same staged save using the existing isolated loader and
checks its marker and pause. In each paused instance two correlated requests
per slot ask MD for the saved registry reference, its current sector, ship
`.idcode`/`.macro.id`, and sector `.idcode`/`.macro.id`. Lua validates each
returned local handle, type, ship-sector relationship and stable local handle
and attributes across the two requests. The local slot-2 handles also match the
prior independent read probe inside that same process. Both ships and both
sectors must be locally distinct. No local handles are compared across
processes. The runner compares each reported tuple to the parsed save tuple.
The getter `sector.idcode` is plausible but not yet established: unavailable,
malformed, mismatching or uncertain output fails the arm instead of providing a
fallback identity. Known X4 conversion/arithmetic, probe, MD and Lua faults
also invalidate the run; the fault filter is not a complete X4 error detector.

Even an exact match is evidence for these two saved slots in these two local
runs only. It does not prove that X4 consumed the exact staged bytes, continuous
pause, universal code uniqueness, permanence after a ship is destroyed or
created, identity reconciliation, sector-frame equivalence, synchronization,
Windows, Internet, or gameplay. The saved parser and live MD checks are not
fully independent: they intentionally refer to the same saved fixture and
registry. The extra saved component/ancestry and attribute checks are separate
from the runtime local-handle checks. Sampling can miss changes between checks;
all relevant game getters and this composition need native verification.

For an explicitly authorized native experiment use
`python tools/dev/authority_sector_fingerprint_live.py --help` and a new
private `.local` output outside the source experiment. Two subdirectories and a
pair result are retained; no existing source result is rewritten. Offline
synthetic tests do not run X4. Importing the runner starts nothing.
