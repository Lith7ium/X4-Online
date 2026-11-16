# Recovered loopback server experiment

`authority_recovered_loopback_server.py` is an opt-in development entry point.
It reuses the isolated Linux X4 recovery/marker/control bridge, checkpoint
store, local TCP control, and participant adapter. It starts no process on
import. It binds both services to `127.0.0.1`; there is no Internet listener.
It does not provide a player client, synchronize gameplay, or establish Windows
compatibility. It must not be used as a playable multiplayer server.

The only allowed initial source is the recorded recovery fixture already
identified by `authority_recovery_join_source.py`. Once an invocation has
ended cleanly with its own confirmed final checkpoint, its `checkpoints`
subdirectory may explicitly be passed as `--store` to a later invocation. Both
source and output must be under this repository's `.local` directory, in
separate trees. Start only while all X4 processes and source writers are
stopped. The later invocation stages a fresh private copy and checks the
confirmed pointer, save hash and MD marker; it also checks the prior result,
`CURRENT` against `CONFIRMED`, and the saved profile content and MD scripts
against the new isolated case. Those checks assume locally controlled files and
are not an authentication mechanism or an atomic fence against another writer.
The marker observed after X4's load event does not prove byte-exact file
consumption or zero simulation before pause.

For an isolated experiment, with a compatible pinned X4 installation,
Bubblewrap and a local X11 display and readable `XAUTHORITY`, the first command
has the following shape (replace placeholders; output must not exist):

```sh
python tools/dev/authority_recovered_loopback_server.py \
  --game /path/to/X4 --display :DISPLAY --out .local/new-server-run
```

Once recovery has been observed, the server writes an owner-only
`endpoint.json` in that private output directory. It contains the loopback
control host/port and file host/port/token/slot; the token is a secret. It is
removed during shutdown. Never expose this file or these endpoints to the
Internet. The controller pumps while connected and while empty: a last
participant disconnect requests pause and a marked save, after which a later
local participant may connect. SIGINT, SIGTERM, SIGHUP or the bounded
`--timeout` end the supervisor. It stops accepting, disconnects tracked
participants and completes pending pause/save operations before stopping X4;
those operations can take longer than the requested timeout. An error or
interruption can instead leave the last operation uncertain, so check
`result.json`; do not infer successful saving from process exit alone. A run
without a new checkpoint has a null `final_checkpoint_id` and cannot be used
as a subsequent source. A valid prior output is selected explicitly:

```sh
python tools/dev/authority_recovered_loopback_server.py \
  --game /path/to/X4 --display :DISPLAY --out .local/next-server-run \
  --store .local/new-server-run/checkpoints
```

The owner controls and process guards are experimental. Runtime state from
high-attention clients is not reconciled by this supervisor, and concurrent
multi-client gameplay, graceful client-side shutdown, reliable HA handover,
crash recovery after unsaved progress, arbitrary X4 saves/content, Windows and
WAN remain unsupported. A timeout can remove connected peers before their local
simulation is incorporated. The source checkpoint remains unchanged; output is
new and private. Never substitute a normal user profile or save.

Offline tests use fake X4 controls and fake load claims. The combined test uses
real local TCP sockets and the real coordinator to exercise a last-disconnect
save, a later second join and a save on controlled shutdown, but it does not
execute this process launcher or X4.

## Recorded native server / simulated client run

On 2026-11-16 the isolated sequence was run once, with artifacts under
`.local/authority-restart-orchestration-01`. The first Linux X4 server recovered
the recorded fixture and served two sequential loopback TCP save downloads.
The second offer identified a new checkpoint after the first disconnect. The
supervisor reported the sequence pause, save, resume, pause, save, resume,
pause, save, with checkpoint publication after each save. Its final marked
checkpoint was `checkpoint-c0b941883c2544949a56fa0df3454a42`, SHA-256
`c17d09c5ca4662ef3f765e9e3a59a4f6507b2a9644978effd42c4a73c0f8a8ca`.

A separate Linux X4 server then staged that checkpoint in its private profile.
Its recovery log recorded a load request, the marker
`61299c3bc5cbe3e2590cbd16bef55844`, and a pause, in order. That marker matches
the first server's final checkpoint manifest; an independent SHA-256 read of
the first checkpoint and the second server's staged `save_008.xml.gz` matched
the digest above. The second server served one further loopback save download
and reported pause, save, resume, pause, save. Its final checkpoint was
`checkpoint-2cf0fd3e281c48f8803b790b59e9d4a0`, SHA-256
`12570e0eb97c7d1effe318be7f1163c158fd35341d37e932e25c1fa84b21d0f1`.
Independent SHA-256 reads of all three downloaded files matched their probe
results. Both supervisor results report a paused final state and no remaining
owned processes; the orchestration result reports cleanup confirmed. Both
temporary endpoint files were absent when checked after the run.

The probe performed real file transfers, but its client-side load request,
loaded-marker observation, pause claim and participant pause/resume controls
were **simulated**. The reported server engine-operation sequence is recorded
by the supervisor, not an independent capture of native control packets. The
marker after the native load event and matching staged bytes do not prove which
exact bytes X4 consumed or that no simulation occurred before pause. This run
does not establish a real client load, playable multiplayer, gameplay,
universe-wide consistency, Windows or Internet operation.

## Recovered server with one real Linux client

On 2026-11-16 the opt-in `--diagnostic-client` path ran once with private X4
profiles and loopback networking. The artifacts are in
`.local/authority-real-client-once-01/server`; the parent orchestration result
is in `.local/authority-real-client-once-01/result.json`. The server's native
log records a recovery request, marker `c4e0b98e123a273edb2551c96f50681f`
and pause in that order. The separate client X4 log records its ticket-bound
load request, marker `3a434ddef339d02ce12146b38831c73b`, two saved fixture
references and pause receipt, in that order. The client save copy hashes to
`324cc3e740f7dac8cff3657d4e11564ee9205308378d446870f383b174b54c74`,
matching the ticket for `checkpoint-aa92d86532a1498699d6c4efda33606d`.
The client-log ordering and file hash were checked again from the retained
artifacts. These checks do not independently establish that X4 consumed every
byte of the staged file.

The supervisor reports a trusted client claim over TCP, admission and native
server/client resume confirmations through the participant-control path; its
result also reports a clean helper exit, final client log/input verification
and confirmed client process stop. These are supervisor and helper receipts,
not an independently retained TCP packet capture. After the client disconnected,
the supervisor reports server pause and save, ending with the paused confirmed
checkpoint `checkpoint-13890e69102c474ca46bea976d0db960`, SHA-256
`4127ff1670de6a488020ac9ae0cab9eb6583c8532c064626049b3e93f7ee5369`.
The final saved bytes were independently rehashed, and the marker
`5d6dac1ea4b95f6dcb117098934fba23` was verified in that checkpoint. The
`CURRENT` and `CONFIRMED` pointers agree, the endpoint file is absent, and
the supervisor reports no owned processes remaining.

The later `serve` loop reports zero accepted and zero admitted connections:
the diagnostic client was accepted before that loop and is counted in the
separate `diagnostic_client` result. No second real client joined this run.
The outcome does not establish Windows, Internet, gameplay, world consistency
or the complete persistent shared-world scenario.

The experimental `--diagnostic-clients 2` option instead prepares two private
Linux client processes in sequence before publishing the endpoint. It waits for
the first connection's EOF, pause and marked save, then requires the second
client's offered checkpoint ID, hash and marker to match that confirmed save.
Each client has separate private artifacts and helper ownership. It does not
test simultaneous clients, gameplay, Windows or Internet access.
During download pumping and UDP enrollment, cancellation is checked between
polls. A synchronous engine or participant command already in progress can
still delay cancellation until its bounded response or timeout; an uncertain
command fences the run and must not be treated as a confirmed checkpoint.

## Recovered server with two sequential real Linux clients

On 2026-11-16 the `--diagnostic-clients 2` path ran once in private profiles
over loopback, with artifacts under `.local/authority-two-sequential-clients-once-01`.
The two separate client X4 logs each record a load request, a marker and a
pause in that order. The second marker is
`d555fa965c14f1f63ac940f635e3e6c0`; its request identifies
`checkpoint-41eece0c14fb48419574bb9b47cb273e`, SHA-256
`81d9f96388c1073765f028e337f83a5848edfc0903d7df4a5678876b7e8c5c9e`.
Independent hashes of each retained client save copy match its corresponding
checkpoint file and ticket. An independent artifact audit also verified the
intermediate and final saved markers. The marker and matching files do not
prove the exact bytes X4 consumed.

The supervisor reports that the first client disconnected, then the server
paused and saved the checkpoint offered to the second client; it reports both
clients admitted and both server/client resumes confirmed via the participant
path. The second departure produced the final paused checkpoint
`checkpoint-c7776916f5924040bc84933cd9269117`, SHA-256
`af3c2d9a13ba7719d271d2edb96dac8c8b9fba2c794f5675f4145f76526e6623`,
which was independently rehashed. These admission and operation-order claims
are supervisor results, not an independent packet capture. The supervisor
reports no owned processes remaining and the orchestrator reports cleanup
confirmed; the independent audit found `CURRENT` and `CONFIRMED` equal, the
endpoint and lock absent, and no X4 processes. The later accept-loop counters
exclude both diagnostic clients.
The clients ran sequentially, not together; gameplay, shared-world consistency,
Windows and Internet access remain unproven.

## Recovered server with two overlapping real Linux clients

On 2026-11-16 one opt-in `--diagnostic-overlap` run used isolated profiles and
loopback; retained artifacts are in `.local/authority-overlapping-clients-once-01`.
Each client X4 log records a load request, its corresponding saved marker and
a pause in that order. The first request identifies checkpoint
`checkpoint-5f54d6a91f2040588b7f4b1ae7944f9a`, SHA-256
`1ebebd2862dfbac0989921150f0600bb006b2156e187aa6196a62986b6396038`,
and marker `25adad4ee7f4c6efd0341b26e0b20fcd`. The second identifies the
different checkpoint `checkpoint-e7cf3c46b0bf493fbbc93cb64dfa435b`, SHA-256
`5b5383e244edf5352c82e63711c72cfc3b89a33d3eb57f6be1ff99f1fee7adf1`,
and marker `f135902caf326e9f252be336fe4a52ae`. The supervisor reports
matching client staged-save hashes and final protected-input checks. The
orchestrator also verifies the retained checkpoint bytes and saved markers.
These observations do not prove exactly which bytes either X4 process loaded.

The supervisor reports both TCP admissions and resumes, two distinct client
PID/start-time identities on the same server PID/start-time identity, and
two active participants before the first client leaves. After that departure,
it reports one participant remaining and the session still `running`. This is
a supervisor state observation: game-time progression after the first
departure was not independently measured. Following the second departure, the
supervisor reports a final paused, confirmed checkpoint
`checkpoint-a8c53cab0d5e4d5886db93aafef41fa9`, SHA-256
`50f0f5e1247d51a44504b33766a78e729c33cdb8ee4a5f0ced06bb90dbdc6bc6`,
with marker `f3c7a8ccdfcaab66a42e86f3c01f8cb2`; the orchestrator checks the
stored checkpoint and marker. The later accept-loop counters exclude these
diagnostic clients. There is no independent TCP packet capture. The supervisor
reports no owned processes remaining and the orchestrator reports cleanup
confirmed.

During the run, a sample of the supervisor's `/proc` I/O counters rose by
approximately 607 MB of `rchar` over two seconds, with no increase in
`read_bytes`; sampled open descriptors included save files. The guard code
repeatedly hashes staged saves, making repeated hashing a plausible contributor,
but this was not a profiler-based attribution or a measurement of its effect
on wall-clock time. This run does not demonstrate two players' controls,
gameplay, universe consistency, Windows or Internet operation.

## Internal diagnostic procedure

The following procedure
requires a dedicated display and the usual owned-process, protected-profile,
Steam-identity and lock checks from the supervisor. It uses the current
recorded fixture; it does not use a real player save. Never start a second
supervisor while the previous owned X4 process or its lock remains.

1. Start the supervisor with a new `.local/server-a` output, a timeout long
   enough for recovery and three saves, and wait until its private
   `.local/server-a/endpoint.json` appears. Confirm its process is still owned
   and alive. Do not print or share the endpoint file: it contains a token.
2. Run `python tools/dev/authority_loopback_simulated_client.py --endpoint
   .local/server-a/endpoint.json --out .local/probe-a --count 2`. The probe
   downloads two saves over actual local TCP and verifies the files and saved
   markers. Its client-side X4 load, marker, pause and participant commands
   are all simulated; no client X4 is started. The second offer must identify a
   newly marked checkpoint, which depends on the first disconnect having been
   processed and saved.
3. Signal the exact owned supervisor process to stop gracefully and wait for
   its owned X4 cleanup. Do not treat a timeout as process termination or start
   a replacement while it remains live. Check `server-a/result.json` reports
   success, an empty `owned_processes_remaining`, paused world, and non-null
   `final_checkpoint_id`/`final_checkpoint_sha256`. An interrupted or failed
   save is indeterminate and must not be silently retried.
4. Start a second supervisor with a fresh `.local/server-b` output and
   `--store .local/server-a/checkpoints`. After its endpoint appears, run the
   same probe with `--count 1`, using `.local/server-b/endpoint.json` and a
   fresh `.local/probe-b`. Stop the second supervisor gracefully and check its
   result and owned-process cleanup in the same way.
5. Run the read-only artifact checker:

   ```sh
   python tools/dev/authority_loopback_restart_evidence.py \
     --first .local/server-a --first-probe .local/probe-a \
     --second .local/server-b --second-probe .local/probe-b
   ```

The checker matches the first final checkpoint to the second server's
recovery source, reads both recovery logs, verifies the transferred and stored
save bytes and markers, and checks recorded native bridge operation sequences.
It does not independently establish exactly which bytes X4 loaded, zero
simulation before pause, any real client X4 load, gameplay, WAN, Windows or
universe-wide state consistency. Its source archives must remain exclusively
controlled and unchanged during the check.
