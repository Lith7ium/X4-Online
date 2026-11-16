# Paused census job and witness owners

These default-off Lua/MD components are internal test fixtures. Import does not
launch X4, install an update handler or open a socket. Explicit X4 binding opens
one connected nonblocking loopback UDP socket. The surrounding disposable
harness owns both isolated profiles and the sole update owner per X4, verifies
checkpoint and archive provenance, gates process startup, keeps the independent
process/lease/deadline/file fences active, and stops/reaps helpers before either
X4 or its lock is released. No Create or Save command is issued here.

The supplied `authority_census_job_baseline.xml` is a read-only client query.
Client READY requires its correlated result to show the saved registry epoch,
`last=10054`, healthy registry and both tables present. It does not independently
revalidate all 10054 bindings. Source READY instead follows the existing
exclusive, paused job-host attach and its baseline/queue checks. The queue is
initialized on the source only, using the saved registry epoch; the fresh
`attempt` is a separate run correlation value. The source resumes only after
the supervisor sends START; the client stays paused.

After the source host reports its first `new_registry_entry`, the owner accepts
only index 10055 and saves the original local actor and separate job sequence.
The report follows a local queue ACK. The owner stops calling the host poll,
requests a pause, confirms it and uses the paused descriptor probe on that
actor. Registered queue/registry fault callbacks remain active. `host:state()`
only checks local host state: it does not query the queue again, exclude added
non-faulting queued events, or establish uninterrupted event coverage. The
existing host's clock/window still runs while paused; a separate conservative
owner deadline fences the capture and transfer period. A missing event, queue
fault, overflow, lost pause, timeout or uncertain operation fails the case.

Only a guarded tick after the descriptor callback emits the descriptor. It
contains `jobseq`, index, macro, faction, sector macro and finite sector
position, never a local actor or sector handle. The source then accepts one
WITNESS command only if the job sequence and sector macro match that descriptor.
The client accepts its own one WITNESS while paused. The supervisor must select
the **same** saved witness index and sector macro from its independently
validated census witness artifact for both processes. Each owner runs the local
witness probe; only a subsequent guarded tick emits WITNESS_OK. A missing,
moved, docked, ambiguous or otherwise unusable witness fails; this owner does
not retry. A caller may treat such a case as inconclusive, not as proof of an
empty sector. `WITNESS_OK` is a local observation, not a TCP acknowledgment.
The supervisor must verify both observations and only then allow the separate
TCP witness ACK. No owner output establishes equal coordinate frames across
processes, an atomic snapshot, event coverage or a newly born ship.

All UDP messages are ASCII `|`-separated, at most 768 bytes. Per-role leases,
the fresh attempt and saved registry epoch bind a single owner. The harness
must bind each observed UDP peer address to its role; loopback and the lease are
not an Internet authentication design. X4 sends:

```
CENSUS|lease|role|attempt|epoch|READY
CENSUS|lease|server|attempt|epoch|DESCRIPTOR|jobseq|10055|macro|faction|sector_macro|x|y|z
CENSUS|lease|role|attempt|epoch|WITNESS_OK|jobseq|saved_index|sector_macro
CENSUS|lease|role|attempt|epoch|CHECKED|counter
CENSUS|lease|role|attempt|epoch|FAULT
```

The harness sends `CMD|lease|role|attempt|epoch|START` to the source only,
`...|WITNESS|jobseq|saved_index|sector_macro` once to each owner, and
`...|CHECK|counter` for fresh guarded observations. Check counters are strictly
increasing positive decimals up to 2147483647, with at most one pending in an
update. Unknown, duplicate, stale or unexpected packets fault the owner. Native
UDP may silently lose datagrams; no mutating request is automatically retried.
Value-free `AUTH_CENSUS_JOB` log markers are READY, DESCRIPTOR, WITNESS_OK,
CHECKED and ERROR FAULT. Fault reporting and the sampled checks are best effort,
not atomic or continuous liveness guarantees. Continue ticking and monitoring
through shutdown; late callbacks are failures.

`authority_census_job_owner_x4.lua` binds the owner to the existing host,
paused-descriptor and runtime-witness modules. The caller supplies their module
objects and a local guard that works during both running and paused phases. It
must install the baseline, paused-descriptor, job-event and witness MD scripts
only in appropriate private overlays, plus the existing saved-state scripts and
native UDP library. Exact script bytes, profile/save files and X4 process
identities remain the supervisor's responsibility.

Focused offline checks:

```
python3 -m unittest discover -s tests -p test_authority_census_job_owner.py -v
```

The tests simulate X4 APIs and callbacks; they do not execute X4, the combined
TCP path, Windows, cross-process frame identity or multiplayer gameplay.
