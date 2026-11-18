# Linux server / Windows-under-Proton TLS admission

18 November 2026. Internal client-first experiment following the
[standalone Windows control observation](AUTHORITY-WINDOWS-ENGINE-CONTROL-20261118.md).

## Result

Pair 02 passed with two actual X4 engines: the existing recovered Linux server
and a Windows X4 client under GE-Proton10-29. The client requested the server's
real offer, downloaded/staged its fresh checkpoint through existing pinned,
authenticated loopback TLS/file transport, observed load/marker/identity/pause,
submitted the existing admission claim and confirmed server-directed resume.
The ordinary full Linux server and shared TLS/admission modules were unchanged.

| Evidence | Recorded result |
|---|---|
| Parent / server / client | Passed; server, preflight and client child exit codes `[0,0,0]` |
| Server connections | 1 accepted, 1 admitted |
| Client participant command | Request 1 resume confirmed |
| Raw client clock observations | 50 total, including 27 paused samples |
| Final continuous resumed observations | 20 unpaused samples |
| Last paused baseline to final resumed sample | Game time 6.5834657 → 10.7415798; advance 4.1581141s |
| First to last of those 20 resumed samples | Game-time advance 3.8689934s |
| Saved registry status | `['uninitialized']`; no fleet/mapping coverage claim |
| Client shutdown | Owned prefix/groups stopped while local owner socket remained open |
| Final server state | Paused, with a new confirmed checkpoint and no owned processes remaining |

Server engine operations were `pause`, `save`, `checkpoint_published`, `resume`,
`pause`, `save`, `checkpoint_published`. Its final checkpoint is
`checkpoint-10cc7f24f7fd432ea39f1c1687bf0f40`, SHA-256
`24729a629358e31107bfc87510e4dffcf46c222f278c9fd45208400a41d60d67`.
The parent sent SIGTERM to the server soon after the client exited. Thus the
final paused checkpoint establishes the combined departure and controlled
shutdown path; it does not separately time or isolate a last-disconnect save.
No restart, rejoin or second participant was exercised. The only client command
was resume; the final pause was observed on the server, not acknowledged by an
already departed client.

## Retained failure and private harness corrections

Pair 01 failed in client preflight before Windows X4 launch: a new ordinary-file
check rejected Steam's legitimate `legacycompat/steamclient64.dll` symlink.
The server accepted/admitted zero connections and exited cleanly in paused state;
parent failure, source/script integrity and cleanup evidence remain retained.

The private client now strictly resolves runtime aliases to regular targets and
pins those identities without relaxing checkpoint/save checks. All independent
runtime validation and input pins run read-only before starting the expensive
server, and normal client preflight shares that helper. Actual installed-path
runtime preflight passed before pair 02. Hot-loop guards compare pinned metadata
(device/inode/size/mtime/ctime), with full hashes at initial/final boundaries;
X4-writable profile XML is excluded from immutable inputs. Shared APIs can close
connections immediately on failure, so cleanup ordering is recorded from actual
local socket state rather than promised for all error paths.

## Isolation and scope

Linux owned both isolated windowed engine lifecycles, the new Proton prefix and
disposable profiles. The original protected source was
`authority-tcp-recovery-01/checkpoints/checkpoint-cdbae20de21c4a47901061374a196c70`;
it remained unchanged. Parent script/source checks and client input/overlay/save
checks passed; Steam identity remained unchanged. Owned native processes, prefix
processes, server and TLS helper were cleaned up. Unreadable unrelated process
environments remain outside this scoped claim. Raw shared-key, TLS private-key
and connection-credential files were retired after cleanup; save/log evidence
stays private.

This was Linux-owned Windows-engine integration, not the assembled native
Windows CLI. No Win32 ACL/KnownFolder/Job ownership, native Windows, WAN,
positions/motion, player flight, gameplay or complete shared world was tested.
Cooperative marker receipts do not independently prove every byte X4 consumed.
No server architecture or GPU behavior changed. Initial-placement/clock decisions
remain pending. No full-suite repeat or game rerun was used for this report.

## Private evidence

Root: `.local/windows-linux-tls-pair-20261118-02/`. Core artifact hashes:

| Artifact relative to evidence root | SHA-256 |
|---|---|
| `result.json` | `f777d1fe665d53cf28cac55f4130434554c478a2d662bb20bc480cd2aaf9d139` |
| `client/result.json` | `b24cdd1e88a5e8374e0595d85724529d6d26b97289fa37977d1fd027861bee14` |
| `server/result.json` | `c4ef5042e57870eac998fd335d20d1e56655acfbc0ade48ce59142e252216ebe` |
| `server/checkpoints/checkpoint-10cc7f24f7fd432ea39f1c1687bf0f40/manifest.json` | `3c65da7894fea0dda2839518ed263bcc3d76ccba44c29095e0d4df5fbfc678a7` |

Exact private scripts are archived under `reproducer/`:
`authority_windows_linux_tls_pair_20261118.py`,
`authority_windows_tls_client_proton_20261118.py`,
`authority_windows_control_proton_20261118.py`, and
`authority_windows_x4_load_proton_20261118.py`. Result records retain selected
script/input pins and engine-log locations. Pair 01 remains in the corresponding
`-01/` directory, including `client-preflight.log` and its archived scripts.
