# Disposable client-to-server bounded pose observations

This default-off diagnostic uses two isolated Linux X4 processes, a synthetic
client-authority grant and local TCP/UDP transport. It follows genuine client
samples for one already saved NPC ship, index 1318 (`WRG-830`), in one sector.
It is not connected to normal gameplay. Before the server resumes, the runner
compares paused, same-run ship and station observations and selects the first
of at most 12 client samples, within 20 seconds, whose distance from the paused
server position is 5–50 units. The paused observation is a candidate filter,
not a proof of uninterrupted pause, a universally shared coordinate frame, or
collision clearance.

After resume, each candidate must bind to the same local actor, sector and zone
and pass a fresh local read-only preflight. A candidate less than five units
away is skipped; a candidate more than 50 units away fails. A READY candidate
is checked again by the write owner, then at most one write is attempted for
that sample. Each `OBSERVED` receipt means only that the diagnostic logged an
immediate local position read after that guarded write. It does not require the
read to match the target and is not the separate one-shot `APPLIED` receipt,
which requires its own delayed readback. The runner permits 2–8 observations
and at most 32 total collected samples; sequences and source game times must
advance. The process stops on a fault or timeout and does not retry an
uncertain write. Source game-time-derived velocity is carried in samples but
is not applied to the server ship. The local distance limits are experiment
guards, not a gameplay movement or collision policy.

The same diagnostic process emits the log markers: they are not an independent
native-call trace. Even matching point observations do not prove sustained
control, equivalent reference frames after resume, HA ownership or transfer,
handling of other ships, collision safety, Windows/WAN, or multiplayer gameplay.

## Attempt 01: two immediate observations

On 2026-11-16, `.local/authority-client-to-server-observe-pair-01/result.json`
reported `success=true` for the bounded observation scope and confirmed owned
process cleanup. This flag describes the diagnostic's checks, not successful
continuous replication or gameplay. The two staged `save_009.xml.gz` copies
currently hash to `64a233ac6a85194b8276212709e78a6c48bbcc0f73c19842622aa098f1408cb8`,
the source hash reported by the runner; the exact bytes X4 actually loaded
were not independently established.

The paused frame comparison reports zero positional delta for the chosen ship
and 11 matched stations at game time 3.037 in both processes. The client log
contains four sequential samples. Sample 3 was selected 26.9288 units from the
paused server ship position. The server log records BIND buffering, READY
preflight, INTENT, WRITE_ENTERED and IMMEDIATE for samples 3 and 4; no NEAR
sample was skipped. Preflight distances were 26.9288 and 30.1623 units. In
both IMMEDIATE records the server position equals the corresponding client
sample target to the printed precision, and the evidence report calculates
zero positional error at each observation.

Between the first immediate read and the second preflight, the reported server
ship position changed by approximately 2.779 units. The records do not identify
what caused that movement and provide no continuous or delayed tracking proof;
the client and server game clocks are separate. The frame screen does not prove
cross-process actor identity or a shared frame after resume. The isolated result
also explicitly records that checkpoint identity, collision clearance, HA
handover and multiplayer are not proven. See the earlier [one-shot attempts](AUTHORITY-CLIENT-TO-SERVER-APPLY-PAIR.md)
for the separate delayed-readback behavior.
