# Isolated source-to-client motion buffer diagnostic

On 2026-11-16, `.local/authority-source-motion-pair-01` returned
`success=false` with a source or participant owner fault and reported that
owned-process cleanup was confirmed. The source X4 log recorded
`binding → attaching → await_go → observing → reading → delivering`, followed
by a generic source `ERROR`. The separate client X4 log recorded a successful
local apply of index 10055 after a witness selection; it did not record a
motion `BUFFERED` marker. The process clocks are not synchronized, and the
logs do not record TCP frames, the source MD acknowledgement, REARM, the
specific faulting component or any actor/sector-binding predicate. Therefore
neither the precise cause nor the outcome of the in-flight job and motion
request is established. No source-to-client motion sample was demonstrated.

After that failed run, bounded opt-in diagnostic reason codes were added for
the source job, local motion IPC and sampler stages. The actor conversion and
dock-check substage can be named without logging actor handles or raw property
values. These codes do not retroactively diagnose the first failed run.

A second isolated attempt, `.local/authority-source-motion-pair-02`, also
returned `success=false` with confirmed owned cleanup. Its client log again
recorded local apply for index 10055; no client `BUFFERED` marker was recorded.
The source log recorded `sampler register_id_roundtrip sampler_register`. This
locates the failure in the sampler's local LuaID identity checks but does not
identify which check failed or the actual returned LuaID type; there is no
packet trace or independently recorded source acknowledgement frame.

The reviewed sampler did contain an incompatible check: it rejected all
opaque Lua `userdata` before converting them back to uint64. The revised code
allows userdata only as an opaque input to `ConvertIDTo64Bit`, then requires
the result to equal the independently retained exact actor uint64. Numeric and
cdata inputs still additionally require an exact direct check. LuaJIT tests
exercise real userdata, wrong and rounded reverse conversions and a uint64
above 2^53. An opaque userdata return is a plausible explanation of attempt 02,
not an observed return type or a proven cause.

A third isolated attempt, `.local/authority-source-motion-pair-03`, returned
`success=false` with `pair context changed`; owned cleanup was reported
confirmed. The source X4 log reached `done`, and the separate client log
recorded `LOCAL_APPLIED 10055`, then
`BUFFERED 10055 1 cluster_115_sector001_macro 13.25216319499998`. The marker
is emitted after the local MD/FFI binding and buffer push but before its UDP
reply. It is therefore provisional evidence of that client-side step, not a
retained TCP receipt or proof of complete delivery. The logs have independent
game clocks and no packet trace; the precise worker outcome is not retained.

The `pair context changed` message identifies expiry of the coordinator's
deadline, capped at 110 seconds, in this run's guard path; other failed lifecycle
checks would have raised their own errors. The terminal-result reader at that
revision performed the full expensive guard before and after every individual
byte. That design can exhaust the deadline on a long result and was replaced
afterward by bounded chunked framing with the same guard/deadline checks and
strict rejection of buffered or newly received trailing bytes. The available
artifacts do not establish whether result reading was the actual cause of this
particular timeout. The revision is tested offline only; this is not a native
successful end-to-end result.

`authority_source_motion_pair_live.py` is a default-off, single-event diagnostic
using the existing private two-X4 lifecycle. It stages the pinned census save
and its historical registry fixture into separate isolated source and client
profiles. The TCP coordinator admission and checkpoint proof are synthetic;
the client's ship creation uses an explicitly artificial seed (7183) and
approximate loadout. An activation is not proof of a ship's birth.

The intended success condition is a source job acknowledged by the client and
the source MD queue, followed by REARM and one sampled source position over
local UDP/TCP to the client. The client performs a correlated local MD/FFI
registry binding and pushes the complete sample to its 3D hold-only buffer
before returning a receipt. The result is correlated with the client BUFFERED
log marker, which by itself is provisional until the receipt and worker result.
The first velocity is unknown, not a fabricated zero. The diagnostic has no
pose/velocity writer and does not prove visual movement, native velocity,
atomic sampling, cross-process sector frame equality, persistence, gameplay,
Windows, Internet transport or complete universe coverage.

The runner inherits the pinned executable/save, load-marker, private profile,
owned-process cleanup and exclusive-lock fences of the existing pair runner.
Both additional local UDP sockets require PID/start/executable/socket-inode
checks by the worker; lease/attempt tokens are fresh. A single update owner per
X4 and one serial TCP delivery owner are required. A blocked motion operation
can delay an incoming job until its own deadline; the test fails closed in that
case and makes no scheduling-liveness claim. The supervisor must fence both
processes and retain profile locks until cleanup is confirmed on any failure.

Offline tests use simulated X4 ABI/MD, and any future native run needs
independent static review, a fresh
private output directory, a display owned by that run and verified cleanup.
