# Experimental source motion sampler

`lua/source_motion_sampler.lua` is a default-off source-side building block,
not an installed update hook or a production motion transport. The existing X4
owner must retain exclusive ownership of registry/descriptor requests and of
its one `onUpdate`; it routes a descriptor event only to the sampler whose
`expected_request()` matches, and calls `tick()` and `event()` serially. The
actual source job owner also uses this descriptor event: its requests and
sampler requests must be serialized or explicitly routed by the sole owner.
A stale, foreign, duplicate or uncorrelated event faults this sampler. There is
no automatic recovery, actor adoption, destruction propagation or movement
writer.

`new_x4` invokes the existing `authority_job_descriptor_probe.new_x4` for each
sample. That reader checks a fresh correlated MD reference against the retained
local actor, validates the registry's forward/reverse mapping, local sector and
FFI component liveness, and samples local sector position between game-time
reads. These checks are not atomic. The caller's `binding_guard` must prove the
entry was actually confirmed by its current source queue/session and must fence
process/load/generation transitions. The X4 factory additionally requires
undocked, not-docking and not-internally-stored readings before and after that
external binding guard. Call `register(row, actor)` only with a
confirmed `new_registry_entry` row and that same process-local actor. Actor IDs
are never present in snapshots. This interface does not yet enumerate or bind
the existing baseline registry; only explicitly registered confirmed new
entries can be sampled. A caller must stop/fence on actor loss, despawn, pause,
docking or other context changes; the current sampler fails the stream rather
than silently dropping an invalid track.

Each tick schedules at most one descriptor request and scans at most the
configured number of tracks. One descriptor request is outstanding at a time,
with a unique nonce-derived ID and bounded timeout. Successful `event()`
returns `true, snapshot`; only then may its caller pass that snapshot to a
transport. If delivery fails after this return, the caller must fence the
session rather than reuse the advanced sequence. The caller must also choose a
fresh nonce with a distinct 16-hex prefix from every descriptor request stream
in the same X4 process, including across sampler recreation. Distinct full
32-hex nonces sharing that prefix are not sufficient. The v1 fields are `version`, `epoch`, `generation`, `index`, a
per-index `sequence`, `sector_macro`, `source_time`, `x`, `y`, `z`, and optional
`velocity`. Lua `velocity == nil` means unknown and must be encoded as JSON
`null`, never as zero. The time is source X4 game time sampled after the local
position read, not a synchronized wall clock. Velocity is derived from local
position differences per source game second, not read from X4. First sample,
sector-macro change, too-short interval, excessive gap or excessive rate
produce an unknown value. A changed local sector reference under the same macro
faults the sampler because the wire cannot express that frame change. The local
reference is used only inside the source process and is never included in the
snapshot. Samples with
unchanged source game time are suppressed without advancing sequence; a local
frame change at the same time still resets rate history. An unchanged position with a valid time interval gives a known
zero. Clock regression, failed bindings, stale responses and timeouts fault the
sampler. Sector macro equality does not establish a common coordinate frame
across different X4 processes.

`python -m unittest tests.test_authority_source_motion_sampler` tests bounded
round-robin scheduling, rate resets and failure fences using simulated inputs,
and exercises the actual existing descriptor reader and X4 factory against a
fake C ABI. No native X4 or network delivery is established by those tests;
no live NPC pose/velocity write, full baseline/world coverage, Windows or
Internet gameplay is claimed.
