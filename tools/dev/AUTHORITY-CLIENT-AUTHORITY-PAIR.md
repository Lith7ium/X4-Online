# Client-authority read-only pair diagnostic

The opt-in Linux/Linux runner prepares two private copies of the pinned save
under the existing load, marker, profile, process and cleanup lifecycle. The
client is given a fresh, explicitly synthetic test grant for saved registry
index 1318 in `cluster_115_sector001_macro`. A synthetic TCP host admits the
client and requests one or two local client samples via the existing admitted
socket and a separately client-PID-/UDP-bound local IPC. The X4 server receives no motion application through this path; no job,
spawn, ACK or server-side position application is claimed. The test uses
disposable profiles and read-only staged saves.

The test-grant callback embeds fresh test values before launch. The worker
must bind the same incarnation once to the actually admitted socket, and must
fence the grant, client PID and local UDP ownership around the request. This is
a test assertion, not real HA assignment or disconnect handover. The client
SAMPLE marker is emitted after its saved registry read succeeds and before IPC
publication, so it is provisional. A successful worker result plus correlated
client markers is required for the runner to report success; neither is a
packet trace. A second sample, if requested, requires an increasing client
game time; velocity is unknown or calculated from local positions per client
game second. The local reads are not atomic and do not establish cross-process
frame identity, gameplay, Windows, Internet operation, or exact checkpoint
file consumption by X4. This setup contains no X4 motion setter.

Only offline tests have been run for the preparation; native execution is not
implied. No normal X4 profile or save is used.

## First native attempt

On 2026-11-16, `.local/authority-client-authority-pair-01/result.json` reported
success with two samples and confirmed owned-process cleanup. The separate
Linux X4 logs record requested checkpoint loads, the expected marker and an
observed pause in each process. The client log then records `RUNNING` at game
time `3.0369999999999999`, followed by two `AUTH_CLIENT_AUTHORITY SAMPLE`
markers for saved index 1318 in `cluster_115_sector001_macro`:

| Sequence | Client game time | Client position `(x, y, z)` |
| --- | ---: | --- |
| 1 | 3.1800227459999997 | (-131813.265625, 1456.1710205078125, -44963.94140625) |
| 2 | 3.3118330659999997 | (-131828.546875, 1456.1064453125, -44950.95703125) |

The saved result reports a completed saved registration and receipt of those
same samples by the synthetic TCP server. It records the first velocity as
unknown (`null`) and the second as `(-115.93363858004439,
-0.48991001093465203, 98.50803032721562)`, derived from the position difference
per **client game second**. The client log markers contain position and game
time, not velocity or the TCP receipt. The worker/coordinator code and saved
result provide the IPC/TCP and sample-correlation evidence; a raw packet trace
or independent raw worker result is not retained.

The test grant and TCP admission/checkpoint claim were synthetic. The result
reports no server-X4 motion application and no owned processes remaining. The
server X4 log does not show applying these samples; the TCP receiver is in the
supervisor's synthetic host, not the server X4 simulation. This bounded result
does not establish exact save-file consumption, atomic position/time reads,
common sector frames, server authority transfer, disconnect handover, visible
movement, combat/trade/boarding, Windows or Internet multiplayer. It does not
prove continuous pause between sampled checks.
