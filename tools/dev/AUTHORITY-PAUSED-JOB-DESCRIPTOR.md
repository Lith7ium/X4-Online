# Paused job-descriptor diagnostic

These default-off Lua and MD files are a read-only experiment. They are not
installed automatically, start no X4 process, register no callbacks and create
no registry consumer or network output. The caller must own the existing job
observer's serialized event queue, retain its reported actor and matching
`new_registry_entry` row, and fence further polling, overflow, timeout, process
identity and exclusive callback ownership until this probe completes or the
entire case is discarded. The queue may already have been locally acknowledged;
this is not an atomic view of the event or proof of a newly born ship. The
caller must treat a successful `response()` as provisional, keep the exclusive
queue, process, pause and deadline fences through controlled use and shutdown,
and fault unexpected or late responses. The core does not maintain a durable
fence after its `done` state.

`authority_paused_job_descriptor.lua` wraps the existing
`authority_job_descriptor_probe.lua` core. Enable explicitly with the same
validated epoch, request ID, row and original local actor. Route the new
`X4AuthorityPausedJobDescriptor.Result` callback to `response`; only one
request may be pending and no other consumer may race it. The MD cue resolves
that same epoch/index, checks the registry forward/reverse binding and excludes
docked or internally stored components. A refusal is correlated and fails the
probe. No MD cue writes game state.

The wrapper requires a successful local paused check and the same finite game
time throughout its observed callbacks. Immediately before and after the FFI
position sample it rechecks pause/game time and requires each of the X4 UI
`isdocked`, `isdocking`, `isinternallystored` getters to return exactly `false`;
missing or unknown values fail. It verifies the original actor against the MD
actor, a valid operational ship and its local sector context before and after
`GetObjectPositionInSector`, and finite coordinates. Local 64-bit actor and
sector values are used only inside this process and are omitted from the
returned descriptor. The exported values are names and position, not a
cross-process handle; the sector macro is not asserted to be a globally unique
sector identity. The generic constructor takes an explicit core module and
injected guards for offline tests; `new_x4` binds real APIs only when explicitly
called in the private X4 environment.

Pause and docking checks are point observations, not a lock: an unobserved
unpause/repause or state change between them cannot be ruled out. MD descriptor,
FFI position and registry checks are not one atomic world snapshot; equality of
reported game times does not prove otherwise. Actor conversion, runtime getter
behavior, saved reference identity and complete queue coverage still require
native evidence. Nothing here sends a descriptor to a client or proves
multiplayer gameplay.

Focused offline tests, including a LuaJIT FFI fake using an actor above 2^53:

```
python3 -m unittest discover -s tests -p test_authority_paused_job_descriptor.py -v
```
