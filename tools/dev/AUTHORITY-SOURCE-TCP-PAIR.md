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
