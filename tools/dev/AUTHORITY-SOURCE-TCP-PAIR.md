# Bounded native source-to-TCP-client diagnostic

On 2026-11-16, `.local/authority-source-tcp-pair-01` reported success for
one selected job activation in two isolated Linux X4 processes on the same
machine. The experiment was explicitly enabled and used private profiles,
staged census saves, local UDP, and loopback TCP. It did not test a Windows or
Internet connection or playable multiplayer.

The two X4 logs each record a request to load the staged census checkpoint,
the expected marker, and a pause observation. They do not independently prove
which file X4 consumed or that it remained paused continuously. The source log
samples `binding`, `attaching`, `await_go`, `observing`, `reading`, `delivering`
and `done`: game time advanced from 3.037 at `observing` to 13.114841807 at
`reading` and 13.202591453 at `done`. These state samples are not a complete
wire or event trace. The client log records `RUNNING` at game time 3.037 and
`LOCAL_APPLIED 10055` at 13.249663382. The logged times belong to different X4
processes and are not a cross-process clock or coordinate-frame comparison.

The worker and coordinator result reports source sequence 1, registry index
10055, macro `ship_gen_m_tugboat_01_a_macro`, faction `pioneers` and sector
`cluster_115_sector001_macro`. The result reports a TCP receipt after client
replica application and the source queue acknowledgement. The supervisor and
worker code correlate the source IPC, TCP delivery, client UDP/MD/FFI path and
actual source MD acknowledgement; the saved result is the evidence that these
checks returned successfully. There is no packet capture or independently
saved raw PID/socket-inode trace. The result also reports no owned processes
remaining after cleanup.

The source was a real X4 job activation and registry enrollment, not evidence
of a newly born NPC ship. Its running descriptor is not an atomic snapshot, and
its source and client coordinate frames have not been proved identical. The
client used an artificial creation seed `7183`, and its created ship uses an
approximated loadout; this is not a complete replication of the ship state.
The TCP server-side checkpoint and admission were synthetic: no save was
transferred to the client as part of TCP admission. This one-event diagnostic
also establishes neither continuous event delivery nor position/velocity
synchronization, persistence, combat, trading or boarding.

The private diagnostic runner can also be explicitly configured with
`--max-events` from 2 through 8. It then requires each consecutive source
sequence and registry index, a validated saved-sector witness for every
candidate, a client receipt and source MD acknowledgement for each event, and
`REARM` before the next. The small count is a resource and runtime bound for
this private experiment; it is not a target or a general universe limit. The
reusable bridge continues to process events serially without that count limit.
The source also has a continuous mode with a point-in-time empty-queue
observation; the native run below used a fixed event count, not that mode.


## Two consecutive source events

The separate opt-in `.local/authority-source-tcp-multi-01` diagnostic reported
success for two consecutive source job activations on 2026-11-16. It used two
isolated local Linux X4 processes and **one** local TCP client. The two
reported descriptors refer to the same sector, `cluster_115_sector001_macro`,
and the same ship macro `ship_gen_m_tugboat_01_a_macro` and faction `pioneers`.
The result records sequence/index pairs `(1, 10055)` and `(2, 10056)`.

Both X4 logs show a request to load the staged census checkpoint, the expected
marker and a pause observation; they do not prove exact file consumption or a
continuous pause. The source log samples `observing` at game time 3.037, then
`reading`/`delivering`, a return to `observing`, another
`reading`/`delivering` and `done` at 13.400771609. These states are samples,
not a complete event or message trace. The client log separately records
`RUNNING` at 3.037 followed by `LOCAL_APPLIED 10055` at 13.229446902 and
`LOCAL_APPLIED 10056` at 13.448099517. Source and client game times are not a
shared clock and cannot independently establish cross-process ordering.

The supervisor's saved result and the worker/coordinator code support the
correlated order for each event: source descriptor, client TCP delivery and
local apply, client receipt, source MD acknowledgement, then REARM before the
next head. TCP frames, individual acknowledgements and PID/socket inode
samples were not separately saved as a packet or raw process trace. The result
reports owned cleanup confirmed with no remaining owned processes.

The TCP server checkpoint and admission were synthetic, and the client used
artificial seed 7183 with an approximated loadout. A job activation does not
prove a ship birth; descriptors are not atomic and cross-process frame
identity is unproven. Two events in the same sector do not demonstrate
complete universe coverage, continuous replication, Windows/Internet
connectivity, persistence or gameplay.

### Continuous-window diagnostic

The separate `--continuous` opt-in runs serial source delivery until the source
reports a correlated `FINISHED` snapshot after its observation window. It uses
no small fixed event-count target. The X4 event producer continues running, so
this reports only a point-in-time queue observation, not a durable drain or
complete universe coverage. Each completed event is sent separately to the
supervisor after client receipt, source MD acknowledgement and REARM. Results
retain the worker-reported completed prefix on failure, and the current event
is marked uncertain. Final X4-log validation is required before a successful
result. A zero-event snapshot is recorded as inconclusive, not as a client
apply. The private runner imposes finite process/time/log and 64 MiB progress
artifact resource limits; hitting a limit is a failure, not a truncated success.
The longer-running reusable components and this private bounded lifecycle have
separate timeout policies. Offline tests exercise more than eight events,
missing-witness failure after a completed prefix, and an empty snapshot with
synthetic process peers.

The one native `.local/authority-source-tcp-continuous-01` attempt on
2026-11-16 **failed** before reporting `FINISHED`. The client X4 log records
19 consecutive `LOCAL_APPLIED` entries, indices 10055–10073, followed by a
generic participant-owner error. The source log samples 20 `delivering`
states; the last sampled state is `delivering`, with no event identity printed
there. The saved supervisor result contains only two completed worker-progress
records, for sequence/index `(1,10055)` and `(2,10056)`. Those records and
the client logs are different evidence: later local applications do not prove
TCP receipts, source MD acknowledgements or REARM. The outcome of the last
begun event is uncertain. The saved result reports no FINISHED snapshot and
confirmed owned-process cleanup with no owned processes remaining.

The immediate cause of the client error cannot be identified from the generic
log. The old supervisor read each frame one byte at a time and ran an expensive
context guard around each read; this could explain why the saved worker prefix
was short, but the original socket buffer contents were not recorded. The
framing has since been changed and tested to read chunks and preserve available
validated progress frames on failure. That change cannot recover the original
run’s unrecorded frames. Subsequent diagnostic error codes are likewise
prepared for future use; they do not identify the original failure. No packet
trace, full-universe coverage, Windows/Internet operation or gameplay success
is established by this failed attempt.
