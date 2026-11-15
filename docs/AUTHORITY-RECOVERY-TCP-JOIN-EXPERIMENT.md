# Recovery followed by one TCP client: isolated experiment

This opt-in diagnostic is prepared for the pinned `.local/authority-tcp-recovery-01` checkpoint. It stages a private copy, verifies the recorded source result, checkpoint ID, digest, size and saved marker, and preserves the archived identity fixture without installing its spawn UI. The isolated server must report the expected load marker and pause before the recovery bridge is activated. It then creates a new marked join checkpoint, offers it to one actual second isolated Linux X4 through loopback TCP and the existing file service, verifies the client's ordered load/marker/pause observations, and forwards native pause/resume through the TCP participant helper.

Both instances use temporary profiles, owned gated processes and the existing bounded cleanup. The helper is stopped before the X4 processes; failure to confirm its exit retains the X4 lock. Source and output directories must be separate. The saved server inputs and installed scripts are protected by read-only mounts and checked at key boundaries and after owned cleanup. Checks are point-in-time, not an adversarial lock on archive writers. The archived identity script matches current bytes, but its historical execution bytes were not independently fenced in the earlier source run.

The marker and client claim are cooperative observations. They do not prove the exact bytes X4 consumed or zero simulation advance. The two fixture references observed by the client do not prove general world identity or gameplay. After the confirmed resume the helper is stopped, closing the control connection; the running session state recorded before that stop does not prove that the session remains usable afterwards. The test says nothing about Windows, internet connectivity, combat, trade, boarding, independent sectors, or a real player logout. A passing synthetic test does not establish a native result. The helper's process and timing controls are test infrastructure, not a final multiplayer architecture.

## Recorded native run

On 2026-11-16, `.local/authority-recovery-tcp-join-01` completed successfully with two isolated Linux X4 instances and loopback networking. The recovered server's log records a request to load `save_008`, both X4 load passes, the expected source marker `c4e0b98e123a273edb2551c96f50681f`, and a pause observation in that order. The staged source file has the pinned SHA-256 `36833a68e8549c6b5ca105db3dbcbc183c0a0257aa9b0a30ff212639d2e2f018`.

The new confirmed join checkpoint is `checkpoint-34bf38a3741247b4bcf8820c51823c56`, 25,769,043 bytes, SHA-256 `cc61cc2d62a9c7f8e7395f88a31b870b0aab936fee459f13575df790d69fcd92`, with fresh marker `b065ac108325e72a5b959c2fa0324b84`. Its saved marker was independently rechecked offline. The client copy has the same digest and its log records load request, both load passes, that marker, the two fixture references and pause observation in order. X4 had an open descriptor on the staged client file with an observed maximum offset equal to its size; this is not proof that all bytes were consumed by the game.

The harness result records a TCP claim accepted, native server and client resume confirmed through TCP participant control, and a clean helper exit. These control outcomes come from the harness and its checked receipts; the archived game logs do not independently contain a TCP packet trace. It reports all owned processes stopped and cleanup confirmed. The client X4 remained a test process and was stopped during cleanup; this was not a real player logout. X4 also logged failed writes to read-only `config.xml` and graphics/signature messages in both instances. The run does not establish a playable shared world or the Windows/Internet target.

A separately reviewed run requires the existing pinned X4 and profile prerequisites, and an empty output directory under `.local`, for example:

```sh
python tools/dev/authority_recovery_tcp_join_live.py --game /path/to/X4 --display :0 --out .local/authority-recovery-tcp-join-01
```
