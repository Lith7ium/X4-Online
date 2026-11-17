# Experimental source motion sampler

`lua/source_motion_sampler.lua` is a default-off source-side building block,
not a production motion transport. The existing X4
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
entries can be sampled by default. A caller must stop/fence on actor loss, despawn, pause,
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

## Explicit saved-baseline opt-in

An owner may separately supply `saved_baseline_limit` and
`saved_baseline_guard(row, actor)` to admit an already locally resolved saved
registry actor. Register that actor with `{epoch=..., index=...,
classification='saved_baseline'}` and **no** job `sequence`. The index must
be within the supplied saved bound. A baseline row is rejected if this pair of
options is absent; the regular `new_registry_entry` route retains its own
`binding_guard` and job sequence. The saved guard is called at registration
and around subsequent reads; it is an external assertion, not proof that X4
loaded a particular checkpoint, that two processes share an actor, or that the
saved bound is genuine. The owner must independently establish and fence
checkpoint/load/process incarnation, the local registry-to-actor reference and
the requested client's current sector interest. No Create or queue receipt is
invented. The unchanged read-only MD descriptor checks local epoch, registry
forward/reverse references and actor/sector; FFI and dock checks still apply.
The descriptor reader admits a `saved_baseline` row only with its separate
explicit saved bound; portable sample sequence remains the sampler's own
per-track sequence, not a fabricated job sequence. A sample still proves no
cross-process coordinate-frame equivalence or world coverage.

This opt-in is a local building block. Existing source session, baseline
resolver/bootstrap, client interest subscriptions and network track ownership
do not automatically connect it to a running X4 session.

## Opt-in source session

The experimental `authority_source_single_job_session` can enable the sampler
and `lua/source_motion_ipc.lua` through its private installer. The existing
single update owner routes both job and motion descriptor responses by their
distinct request IDs. It retains an actor locally only after the matching job
has reached the real host's MD acknowledgement and the correlated REARM has
been accepted. The handoff remains provisional until the owner callback and
its guards return successfully; any uncertainty fails the session. At most one
confirmed actor is registered per update and the pending handoff queue is
bounded. This covers confirmed queue entries only, not the saved baseline.

The separate loopback UDP endpoint uses a fresh lease, attempt and generation.
Its HELLO/BOUND/ATTACHED handshake precedes strictly consecutive PULL requests;
each request receives one correlated SAMPLE or NO_SAMPLE. The packet contains
no actor handle, and unknown velocity is encoded as `-|-|-`. The Python owner
must independently validate and keep fencing the source process and UDP socket,
bind each index only after the corresponding job acknowledgement and REARM,
and wait for TCP delivery before the next pull. A NO_SAMPLE response does not
prove an empty universe or a complete sampling pass. Owner, transport or
callback failures fence the experimental session; there is no implicit retry
of a consumed sample.

`tests.test_authority_source_job_motion_integration` exercises the actual
session, job owner, gate, sampler and local IPC together against simulated
host/MD, network and X4 ABI. It establishes routing and confirmation ordering
offline, not native X4 operation, cross-process frame equality, movement
application or a complete client/server integration.

## Local pair diagnostic

The recovered source owner has an experimental opt-in that takes two local
reads from one explicitly selected saved-baseline actor during an outstanding
PULL. A separate sampler and reserved request prefix keep the diagnostic pair
apart from the normal sampler. After the pair has completed and stopped, the
normal sampler produces the PULL's single response; pair values are not sent
as that response. The owner faults on late pair events and does not acknowledge
STOP while a pair read remains pending. Existing host and save guards are not
removed by this diagnostic.

The optional report describes a position-derived rate per source game second,
not native X4 velocity. Tests exercise the Lua owners with simulated X4 and
transport. The recovery installer and supervisor do not yet expose this option,
and the diagnostic has not been run natively or demonstrated smooth movement,
cross-process identity or frame equivalence, or velocity delivery to a client.
