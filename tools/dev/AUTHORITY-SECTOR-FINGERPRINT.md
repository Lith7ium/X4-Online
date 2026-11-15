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
`.idcode`/`.macro.id`, and sector `.macro.id`. Lua validates each
returned local handle, type, ship-sector relationship and stable local handle
and attributes across the two requests. The local slot-2 handles also match the
prior independent read probe inside that same process. Both ships and both
sectors must be locally distinct. No local handles are compared across
processes. The runner compares each reported tuple to the parsed save tuple;
the saved sector code is not part of the live comparison. The 152 saved sector
macros were distinct in this pinned checkpoint, not shown unique in every game.
Unavailable, malformed, mismatching or uncertain output fails the arm. Known
X4 conversion/arithmetic, probe, MD and Lua faults
also invalidate the run; the fault filter is not a complete X4 error detector.

Even an exact match is evidence for these two saved slots in these two local
runs only. It does not prove that X4 consumed the exact staged bytes, continuous
pause, universal code uniqueness, permanence after a ship is destroyed or
created, identity reconciliation, sector-frame equivalence, synchronization,
Windows, Internet, or gameplay. The saved parser and live MD checks are not
fully independent: they intentionally refer to the same saved fixture and
registry. The extra saved component/ancestry and attribute checks are separate
from the runtime local-handle checks. Sampling can miss changes between checks;
the native observation below does not validate these getters in other contexts.

For an explicitly authorized native experiment use
`python tools/dev/authority_sector_fingerprint_live.py --help` and a new
private `.local` output outside the source experiment. Two subdirectories and a
pair result are retained; no existing source result is rewritten. Offline
synthetic tests do not run X4. Importing the runner starts nothing.

On 2026-11-15, the first profile of `.local/authority-sector-fingerprint-01`
loaded the checkpoint, reported the expected marker and pause, and completed
the initial slot-2 read. Its first fingerprint callback then failed with
`ERROR sample`; the diagnostic at that time did not identify the failing
check. No fingerprint row was accepted, the second profile was not started,
and owned-process cleanup reported no remaining processes. This run does not
establish whether a getter was unavailable, a field had an unexpected format,
or a local binding failed. Callback diagnostics now report the failing check
and, for invalid tokens or rows, limited non-sensitive shape information;
they do not weaken the checks or turn this failed run into evidence of identity.

The next isolated attempt, `.local/authority-sector-fingerprint-02`, again
loaded the marker and observed the pause, but its first slot-1 response
reported `sample_sector_code shape_null`. The second profile did not start;
cleanup reported no remaining processes. This establishes that the queried
sector getter formatted as `null` in that response, not that all sectors lack
an ID-code getter. The current diagnostic omits that getter and narrows the
comparison to ship code, ship macro and sector macro; the older failed runs
are retained unchanged. The subsequent narrower native result is below.


## Narrower native observation

On 2026-11-16, `.local/authority-sector-fingerprint-03` completed both
sequential disposable Linux profiles against the recorded checkpoint. Each
reported the expected load marker and pause, then four correlated rows in
slot order 1, 2, 1, 2, at reported game time 3.014. In both profiles, slot 1
reported ship code `LBT-457`, ship macro `ship_kha_m_fighter_01_a_macro`, and
sector macro `cluster_33_sector001_macro`; slot 2 reported `ABC-309`, the same
ship macro, and `cluster_45_sector001_macro`. All rows matched the separately
parsed saved component/sector fingerprints. Within each profile the Lua probe
checked the returned local ship/sector handles and their relationship, the
repeated-handle consistency, distinct slots and the earlier slot-2 handle.
The result reports no owned processes remaining in either profile; profile 1's
result was written before profile 2's logged start. Both staged saves currently
hash to the pinned source digest.

The monitored conversion, arithmetic and probe/MD/Lua errors do not appear in
these logs. X4 still logged startup errors for the read-only config, Vulkan/FSR3
queue and missing extension signature; diagnostic receipts themselves use the
error log level. The fault filter does not cover every engine problem. No
sector ID-code getter was used in this narrower test: the failed `-02` result
remains unchanged. These observations support the saved attribute match for
two slots in two **sequential** instances; they do not independently prove the
full bytes X4 read, continuous pause, durable general object identity,
sector-frame equivalence, simultaneous clients, movement replication or
multiplayer.
