# Two-X4 admission and native resume diagnostic

This disposable Linux-only diagnostic extends the two-process identity experiment.
It saves in an isolated server profile, transfers a checkpoint over loopback,
and verifies its size and hash before staging it read-only in an isolated client
profile. The client reports its ticket-bound load request and paused state; two
saved fixture references must match before admission. Process identities are
checked and both X4 instances remain owned by the supervisor.

**Test assumption:** the diagnostic treats those observations as confirmation
that X4 loaded the exact offered save, solely to exercise `mark_loaded`. They do
not establish that X4 read all the staged bytes. This must not be used as a
trusted load confirmation for real clients. A sampled file descriptor is not a
proof of a full read either.

After admission, the coordinator requests resume and the server and client each
independently confirm that their native game time advanced while unpaused. A
second simulated join requests pause and both native controllers must observe a
stable paused clock. The second join is only a local trigger; it has no client.
The participant channel is a single-use loopback diagnostic, not a multiplayer
transport. It allows only pause and resume and faults on uncertain results.

The source is opt-in and does not start X4 on import. The supervisor requires a
fresh private output directory, a virtual local X11 display, the pinned Linux
executable and bubblewrap; existing user saves are not used. It cleans up its
owned processes. Consult the earlier two-X4 experiment for the isolation and
checkpoint details. Synthetic socket tests do not prove X4 behavior. No
Windows, external network, live player controls, shared-world replication,
combat, commerce, boarding, or game-client authentication is tested here.

On 2026-11-15, one isolated Linux/Linux run completed this diagnostic. The
checkpoint transfer and the two fixture-reference checks passed. Under the
explicit load-confirmation assumption above, the coordinator admitted the
client; native controls then confirmed advancing game clocks in both X4
processes and subsequently confirmed stable pauses in both. Both owned
process groups were stopped. The clocks were observed independently: this
does not show equal or coordinated simulation state, synchronized ship
motion, an actual second joining client, or any shared gameplay.
