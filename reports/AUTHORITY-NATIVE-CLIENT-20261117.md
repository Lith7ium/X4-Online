# Independent native Linux client observation

17 November 2026. Internal development evidence on the authoritative fork.
Client work takes priority while the user investigates a hosted test server.
The successful trial used implementation commit `b895d498`.

## Result and scope

The independent native client completed a bounded checkpoint join over pinned,
authenticated loopback TLS. One real X4 client loaded the downloaded save,
reported the saved marker and pause, received admission, and confirmed one
server-directed resume followed by one server-directed pause. Exit status was
zero; owned native processes, host thread, TLS and private display were released.

The host used production checkpoint, admission and TCP participant adapters,
but its engine was simulated. Its save operation returned an unchanged,
previously verified checkpoint. An internal join placeholder triggered the
pause; it was not a second player. No native server, Windows client, Internet
connection, movement playback or gameplay was tested. The cooperative marker
claim is not independent proof of every byte loaded (`exact_loaded_file_proven=false`).

## Implementation

- `tools/dev/authority_client_native.py` owns one private Linux X4 process and
  one client owner through offer, download, load observations, admission and
  active controls. It does not instantiate a server or world coordinator.
- `src/authority/experimental_client_session.py` runs TLS on an owned thread,
  leaving native process control on the main thread. Native cleanup completes
  before the connection is released. Cleanup uncertainty prevents success.
- The CLI reuses existing load/marker probes and native participant controls.
  It checks process identity, Steam identity, protected files and deadlines.
  Secrets are read from private files; results use fixed diagnostic codes.
- The save and probes are read-only in X4's disposable namespace. Normal
  profiles and the game installation remain outside the writable test scope.
  The client used its ordinary hardware graphics path; this was not another
  GPU-free server test.

## Attempts and fixes

| Retained attempt | Observation | Correction |
|---|---|---|
| `20261118-01` | Failed during download/staging, before X4 launch | Removed duplicate verification. `copy_to_new_slot` requires the downloaded state and performs verification itself. |
| `20261118-02` | Native load, correct marker and local pause succeeded; claim rejected | Removed a post-verification `chmod` that changed the file's change time. X4's read-only bind remains; fingerprint checks were not weakened. |
| `20261118-03` | Accepted admission, native resume and pause, confirmed cleanup | Passed after both fixes. |

Directory labels contain `20261118`; the successful result was written on
17 November at 23:23 CET. Earlier failed results remain unchanged.

## Validation

The initial affected batch passed **80 tests in 16.464 seconds**, covering native
CLI, connection, participant controls, client owner, native worker/motion,
marked load and two-X4 resume helpers. The first state fix passed 20 focused
tests in 5.324 seconds. After the metadata fix, **21 focused tests passed in
5.613 seconds**, running `test_authority_client_native` and
`test_authority_experimental_client_connection`. The latter uses real local
TLS and a real owner through simulated load observations and actual admission;
a negative case verifies that deliberate metadata changes still reject claims.
No redundant full-suite run was performed. Its earlier failure and missing
prerequisites remain unresolved.

Native trial 03 reported:

| Evidence | Result |
|---|---|
| Ordered load request / inspected marker / pause | All observed |
| Admission | Accepted |
| Server resume / pause confirmations | 1 / 1 |
| Native processes remaining after cleanup | None |
| Host thread / TLS / owned cgroup cleanup | Confirmed |
| Private Xauthority cleanup | Confirmed |
| Selected source pins and Steam identity | Unchanged |

The source was the retained `authority-tcp-recovery-01` checkpoint
`checkpoint-cdbae20de21c4a47901061374a196c70`, 25,791,661 bytes, SHA-256
`36833a68e8549c6b5ca105db3dbcbc183c0a0257aa9b0a30ff212639d2e2f018`.
Its archived saved-state script and private content configuration were checked
before launch. No remote mod download or normal-profile save was involved.

## Retained evidence and next step

Private evidence remains under `.local/private-independent-client-native-20261118-03/`:
`result.json`, `trial-result.json`, `coordinator-result.json`,
`native-client/result.json` and the private profile's `engine-output.log`.
The reviewed manifest is `.local/authority-independent-client-reviewed-20261118-03.json`;
the three harness files are `.local/authority_independent_client_{scope,coordinator,trial}_20261118.py`.
Credentials, saves and raw private logs are not committed. Source checks cover
selected dependencies before/after the run, not every import or intermediate
mutation. Process isolation assumes no external migration out of the owned scope.

Focused logs are in `../x4-authority-throttle-timing-20261117/.local/`:
`client-native-affected-20261117.log`, `client-native-staging-state-20261117.log`
and `client-native-fingerprint-20261117.log`.

Next, connect buffered motion to repeated native playback, starting with an
enrolled disposable ship and actual-position readback. Existing LAN playback,
velocity expiry and coordinate guards are reusable evidence. Separate player
control, Windows integration, real native server/client operation, WAN and the
shared-world gameplay acceptance remain outstanding. Broader ownership and
server execution decisions still require discussion with the user.
