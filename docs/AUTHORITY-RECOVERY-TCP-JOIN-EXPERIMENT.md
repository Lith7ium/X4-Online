# Recovery followed by one TCP client: isolated experiment

This opt-in diagnostic is prepared for the pinned `.local/authority-tcp-recovery-01` checkpoint. It stages a private copy, verifies the recorded source result, checkpoint ID, digest, size and saved marker, and preserves the archived identity fixture without installing its spawn UI. The isolated server must report the expected load marker and pause before the recovery bridge is activated. It then creates a new marked join checkpoint, offers it to one actual second isolated Linux X4 through loopback TCP and the existing file service, verifies the client's ordered load/marker/pause observations, and forwards native pause/resume through the TCP participant helper.

Both instances use temporary profiles, owned gated processes and the existing bounded cleanup. The helper is stopped before the X4 processes; failure to confirm its exit retains the X4 lock. Source and output directories must be separate. The saved server inputs and installed scripts are protected by read-only mounts and checked at key boundaries and after owned cleanup. Checks are point-in-time, not an adversarial lock on archive writers. The archived identity script matches current bytes, but its historical execution bytes were not independently fenced in the earlier source run.

The marker and client claim are cooperative observations. They do not prove the exact bytes X4 consumed or zero simulation advance. The two fixture references observed by the client do not prove general world identity or gameplay. After the confirmed resume the helper is stopped, closing the control connection; the running session state recorded before that stop does not prove that the session remains usable afterwards. The test says nothing about Windows, internet connectivity, combat, trade, boarding, independent sectors, or a real player logout. A passing synthetic test does not establish a native result. The helper's process and timing controls are test infrastructure, not a final multiplayer architecture.

No native run is implied by installing this file. A separately reviewed run requires the existing pinned X4 and profile prerequisites, and an empty output directory under `.local`, for example:

```sh
python tools/dev/authority_recovery_tcp_join_live.py --game /path/to/X4 --display :0 --out .local/authority-recovery-tcp-join-01
```
