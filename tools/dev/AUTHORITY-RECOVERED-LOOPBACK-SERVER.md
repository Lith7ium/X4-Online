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

A later guard change reduces nested duplicate server-file hashes in the overlap
path. Focused offline tests check the retained file, process, worker and peer
checks and failure handling; the timing of every individual hash is not
identical to the recorded run. Its effect on native runtime has not been
measured.

The overlap diagnostic now installs a separate, read-only loopback clock
observer in its disposable server case. After the first EOF and while the
remaining participant is guarded, it requests two correlated observations of
the server X4 pause flag and game clock. It requires both to report running
and the second game time to increase before allowing the second departure.
Focused loopback and supervisor tests use simulated observer responses.

A subsequent isolated Linux run with this observer is recorded in
`.local/authority-overlap-clock-once-01`. After the first participant's EOF
and while the supervisor reported one remaining participant, it reports two
correlated, unpaused server-X4 game-time observations: `30.117642696000075`
and `34.040424454000075`. After the second departure it reports a paused
checkpoint `checkpoint-774a1c96f5544dfaa5b1ce3c5f88e9f2`, SHA-256
`21c0cce9ec5d6bd97abc5f7ec640c0f0556e783b0838bc99cc8c2dde11861e33`,
and no owned processes remaining; the orchestrator reports cleanup confirmed.
The later accept-loop counters exclude the two diagnostic clients. These are
supervisor results with no independent UDP or TCP packet capture. The samples
do not establish uninterrupted progress between them, exact loaded file
consumption, gameplay, Windows or Internet operation.

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

## Optional read-only registry status

`--registry-status` installs the current experimental registry script and a
single status owner in the existing private recovery update. It does not
initialize the registry or enroll ships. The source's marked checkpoint is
inspected first; a saved initialized registry must have a verified bijection
and all indexed saved components, and the source's original MD script must be
available and byte-identical. Uninitialized is also a valid status. Unsupported
empty initialized states, missing or destroyed saved entries and ambiguous
state fail closed. This check is not a complete inventory.

After the recovered load marker and pause, the owner requests a correlated
status before allowing bridge activation. Before each save marker it requests
a fresh correlated status while paused. The supervisor checks the matching
marker-tagged status and compares the newly published checkpoint's registry
epoch, count and canonical saved index-to-component mapping fingerprint with
the source before confirmation. Changed mappings fail closed; saved references
are not independently proven stable across saves or equivalent live actors.
The mode deliberately rejects changes to the baseline until registry
lifecycle handling is implemented. It does not prove which file X4 consumed,
cross-process identity, Windows, Internet or gameplay.

On 2026-11-16, `.local/authority-registry-status-once-01` failed after the
native server paused and saved. Its log records an uninitialized registry
status after recovery and before the save marker, but the candidate checkpoint
was not confirmed: the saved `State` cue was `waiting` with no children, a
native representation the verifier did not yet recognize. The supervisor
reported `ambiguous saved registry`, an empty owned-process list, and the outer
orchestrator reported confirmed cleanup. A later read-only inspection with the
corrected parser recognized the saved state and verified its marker; it did
not confirm or republish that checkpoint.

A fresh run, `.local/authority-registry-status-once-02`, reported success.
One isolated Linux X4 server recovered a marked checkpoint; its log records the
load request, source marker and pause, followed by uninitialized registry
status at startup and before the new save marker. One local offer-only TCP
connection triggered the save; no client X4, download, or load claim was
used. The supervisor reported the server paused and no owned processes left.
The orchestrator reported confirmed cleanup and checked the log against the
nonce from the installed overlay. The confirmed checkpoint was
`checkpoint-7c464277153f42aaa0e649c7c3b85431`, SHA-256
`999897ec96fd01699b7b561e35f8204678408e9769c918cbf08a8c28b948867d`,
with marker `b8a51230f68b1b23abb88593cac07f31`.

The log lines do not contain the registry request ID; the installed owner
checks it before emitting the status. There is no independent packet capture
of that exchange. This run exercised only the uninitialized state, not an
initialized register, ship enrollment, cross-process identity, client loading,
gameplay, Windows or Internet operation. It does not independently prove which
save bytes X4 consumed.

## Optional initial enrollment of observed ships

`--registry-enroll` is an experimental bootstrap for an uninitialized saved
registry. The recovered paused X4 source must report an uninitialized registry
before the owner initializes it with a new epoch. It enumerates eligible
existing ships from observed faction lists, then enrolls them through the
correlated registry owner. Before the first checkpoint is confirmed, its
saved epoch, count and verified index-to-component mapping must match the
bootstrap result; later saves compare the saved mapping fingerprint. A source
with an existing registry is refused. This bootstrap does not establish that
faction lists contain every ship in the universe, and it is not running
creation, destruction or movement replication.

On 2026-11-16, `.local/authority-registry-enroll-once-01` reported success for
one isolated Linux X4 recovery. The census log reports 202,331 enumerated
faction-list entries and 10,082 distinct eligible selected ships, explicitly
with `coverage=unknown`. A local TCP connection requested a save offer only;
no client X4, save download or load claim took place. The supervisor recorded
`pause`, `save` and checkpoint publication, one accepted connection, zero
admitted clients, a paused final world and no owned processes remaining. The
orchestrator reported cleanup confirmed, checked the source and resulting
checkpoint pointers, source integrity, startup and pre-save registry receipts,
the save marker, the offered checkpoint and the saved mapping. These are
supervisor and saved-file observations, not an independent packet capture or
proof of the exact bytes loaded by X4.

The confirmed checkpoint is `checkpoint-6c9b4ce5f0454fe4b3887bc36c213d9f`,
SHA-256 `ce2de5d179017a404a95906c6a394a0ecd7e556c0049a78b60c1a4699d14b19f`,
marker `f5b0355349b7c56f4891915298186ea6`. Its saved registry has epoch
`4ba7be438ebb04ec5bb85fdb95b5a488`, count 10,082 and mapping SHA-256
`6f5cadcc614831d49c143d020d1673f25cbd96a25c04dd5ded5c68d61b6040c7`.
No client has been shown to restore this register, and neither client-to-server
identity nor complete universe coverage follows from this run. Windows,
Internet access and gameplay were not tested.

The full check executed 4,215 tests with one UDP socket-guard error and 56
skips. The affected test passed in isolation; the full-run error remains
unexplained, and the repository's no-skips check is not satisfied.

## Initialized registry recovery failed before client start

The follow-up `.local/authority-registry-recovered-client-once-01` attempted
to recover the confirmed 10,082-entry checkpoint above and then start a real
Linux X4 diagnostic client. The server log recorded the recovered marker,
pause, registry status and a new save. The supervisor stopped with
`checkpoint registry differs from recovered status` during that save, before
client startup or admission. Its result reported no owned processes remaining;
the orchestrator reported confirmed cleanup. The newly published candidate
`checkpoint-96f563f9122144c7a82a82e42bd36b26` remained **unconfirmed**.

Read-only verification of both saved registries found valid forward/reverse
bijections and 10,082 referenced ship components in each, with the same epoch
`4ba7be438ebb04ec5bb85fdb95b5a488` and count. The original mapping fingerprint
was `6f5cadcc614831d49c143d020d1673f25cbd96a25c04dd5ded5c68d61b6040c7`;
the new fingerprint was
`9ab23dfdcda16cb512bdf36716a66ef57c4cf30ab480e096462d7875c9c99f3e`.
Every registry index pointed to a different saved component ID. Of the IDs,
519 appeared in both sets and 9,563 appeared only in each respective set. At
every index, the saved components' `class`, `macro`, `owner` and `code`
attributes agreed; `connection` agreed for 10,078 indices and differed for
four. Code uniqueness or non-emptiness was not established.

The observations are consistent with component IDs being renumbered when X4
loads and saves, but those attributes are not an independently established
identity guarantee. The fingerprint hashes raw saved component IDs and is not
stable across these two saves. The unchanged guard rejects the mismatch; the
candidate is not promoted or made a source. This result does not demonstrate
client registry loading, cross-process ship identity, gameplay, Windows or
Internet connectivity.

## Private saved-registry witness diagnostic

The optional `--registry-witness create` and `--registry-witness verify`
phases are isolated diagnostics: each starts one owned Linux X4 process on a
private recovery copy, requires pause, and saves a private marked checkpoint.
They do not start a client or publish a client endpoint. Create builds separate
forward and reverse witness tables using slots in reverse registry-index order;
verify loads the create checkpoint in a second X4 process and checks each
registry entry against the saved witness and reverse references. The Lua owner
requires correlated replies and logs a single completed-phase receipt; the log
is not an independent capture of every reply. Saved checkpoint verification
checks the registry and witness tables, references and marker in the saved
bytes. The diagnostic may tolerate changed raw saved component IDs; the
ordinary registry recovery guard and its fail-closed fingerprint comparison
are unchanged. A witness checkpoint is accepted as a subsequent diagnostic
source only with the expected script provenance and successful cleaned-up
supervisor result. Diagnostic confirmation happens after owned X4 termination
and final checks; a confirmation error after pointer replacement or a later
result-write failure can still leave a visible pointer, which alone is not an
eligible source.

On 2026-11-16 the first attempt,
`.local/authority-registry-witness-once-01`, logged a sealed create receipt
for 10,082 entries, then rejected its save because the original parser expected
integer counters and slots where X4 wrote canonical `largefloat` values. The
candidate stayed unconfirmed. A later read-only check with the corrected
parser verified its marker and the saved table relationships; that does not
retroactively confirm the failed attempt or prove a reload.

The second attempt, `.local/authority-registry-witness-once-02`, encountered
an event-handler assertion followed by a bridge error before a create receipt.
The event payload and exact failing predicate were not recorded, so its root
cause remains unknown. The owned orchestrator was stopped with SIGTERM; its
result reports `success=false`, confirmed cleanup and no remaining owned X4
processes. The diagnostic now logs bounded failure categories and its owner
polls for known error tags during guarded waits. A blocking adapter operation
can delay detection until it returns or times out.

The third attempt, `.local/authority-registry-witness-once-03`, completed both
phases on the pinned 10,082-entry source. The create X4 log records its source
marker, pause, registry status and a sealed create receipt; the second X4 log
records the create checkpoint's marker, pause, registry status and a sealed
verify receipt. The orchestrator reports both saved structures and markers
verified, no client admission, and clean owned-process shutdown. The create
checkpoint `checkpoint-f3bfb3fc65ad4a93b199230755601f62` has SHA-256
`2b07a55d0d5fda0ef08de8a6b9a562100d745ae39076d1a7092f5e3c150f5994`;
the verify checkpoint `checkpoint-c9b65412fec543ae92115a643fdfd626` has SHA-256
`867406a63b4fdc73ffe208ba4d8aee37bb9d737213c51928187b667c6e917e0b`.
The raw registry mapping fingerprints differed across source, create and
verify: `6f5cadcc614831d49c143d020d1673f25cbd96a25c04dd5ded5c68d61b6040c7`,
`4498b099b8741fccbe1f189cbcb7e8da5a7b08de48d7d57e0caf95baa692e72a`, and
`2dcae0710b427e40832a5428f5f857a8fa79e42f059b77d817d85f32fb4a06dd`.
This demonstrates the observed diagnostic checks and saved relationships,
not which exact file bytes X4 consumed. The registry and witness tables share
X4's serializer and originate from the same objects, so a consistent joint
remapping would also pass: the test does not independently prove historical
object identity, complete universe coverage, or cross-client synchronization.
No client was admitted, and gameplay, Windows and Internet were not tested.

### Prepared private witness join experiment

The opt-in `--registry-witness-join --diagnostic-client` path accepts a clean,
confirmed `create` witness source from this supervisor with the matching saved
scripts. It verifies the server-side witness after recovery, checks the saved
registry and witness relationship at each checkpoint, and uses the existing
one-client load, admission, resume and last-disconnect save path. The listener
is bound to loopback and is never published; after the private client exits,
no further clients are admitted. A saved witness script is installed on the
client, but the existing client observation checks only registry epoch and
count, not the witness or cross-process object identity.

This diagnostic deliberately permits changed saved raw component IDs, whose
relationship is checked against the saved witness in this experiment. It does
not change the regular recovery fingerprint guard or establish independent
historical identity. A confirmed checkpoint pointer alone is not usable
provenance: cleanup and supervisor result must also succeed; join outputs do
not satisfy the `create` witness-source requirement or ordinary recovery's
script-set guard. On isolated Linux runs, the server recovered the source and
verified the 10,082-entry witness, but neither attempted join reached a client
X4 process. One run ended with a disconnected remote-load helper; another
timed out after requesting a server save. The latter did not confirm its
candidate checkpoint. Both runs reported owned-process cleanup. Neither is
evidence of successful admission or gameplay.

The remote-load helper's deadline is now bounded to its own accepted range.
The recovery probe also stops periodic HELLO packets after activation, and the
local bridge drains queued HELLOs before a new command. A loopback UDP test
showed that enough queued HELLOs can otherwise drop the subsequent receipt;
the precise cause of the native timeout was not recorded and is not proven.

In a subsequent isolated run using the original source checks, the new server
checkpoint was confirmed and a Linux client loaded it, observed its marker,
and reported the registry epoch and 10,082 entries. The operator cancelled the
run after more than 20 minutes without another visible join milestone while
the supervisor was repeatedly validating the source. Owned-process cleanup
was confirmed. Admission, resume and the final disconnect save were not
established by this run.

The `verify` witness path uses a pinned source guard after its full initial
validation. Repeated checks hash the compressed source and inspect the
confirmed pointers, manifest and file identities, without repeatedly parsing
the same XML. Source-script and staged-copy checks remain separate. This guard
does not fence a writer and does not establish historical object identity;
the supervisor must retain its existing source and process isolation.
