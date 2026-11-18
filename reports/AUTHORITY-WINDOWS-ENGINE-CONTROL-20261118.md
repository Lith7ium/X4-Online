# Windows engine pause/resume control under Proton

18 November 2026. Internal client evidence after the
[checkpoint-load diagnostic](AUTHORITY-WINDOWS-ENGINE-LOAD-20261118.md).

## Observed result

Actual Windows X4 9.00 under GE-Proton10-29 loaded the retained native05
checkpoint, returned the correlated marker, both named identity fixtures,
10,082-entry registry header and pause receipt, then completed one existing
UDP participant resume/pause cycle. Attempt 03 returned `engine_control_observed`,
exit zero. Production control modules and packet formats were unchanged.

| Observation | Result |
|---|---|
| Request 1: resume | Confirmed |
| Request 2: pause | Confirmed |
| Raw clock samples | 34: 3 loaded-paused, 21 resumed-phase, 10 paused-phase |
| Loaded-paused baseline | All 3 samples paused at game time 7.658786999999999 |
| Resumed-phase evidence | 19 unpaused samples; last two game times strictly increase |
| Game-time advance from baseline to final resumed-phase sample | 3.9011855000000137 seconds |
| Paused-phase evidence | Final 7 samples paused at game time 12.218637800000014 |
| Final 3 paused samples | Same game time across 0.40277880000000366 real seconds |
| Connected UDP ownership samples | 83 successful Linux process/socket/fd checks |
| Command retries | None |

Phase labels identify reader windows, not exact command boundaries: the resumed
window begins with 2 buffered paused samples, and the paused window with 3
buffered unpaused samples. The raw observer samples game time and paused state
in the existing participant update frame, separately from the UDP receipt.
It does not impose a one-to-one real/game clock rate or change clock mapping.

Existing `authority_control_state.lua` confirms resume only after observing unpaused state
and game time greater than the command's starting time. Pause confirmation
requires paused state with unchanged game time for at least 0.1 real seconds.
The additional numeric observations above establish a longer final stable
interval without changing these production semantics.

## Ownership correction and retained failures

Attempts 01 and 02 each completed the correlated load observations, then failed
process discovery before any participant command. Attempt 01 required the process
name `X4.exe`, although the real game renames its main thread `Main()`. Both
initial predicates also compared the device text from `/proc/PID/maps` directly
with `stat` device values. Removing the name filter alone did not fix attempt 02.

Read-only inspection of the running Steam executable showed the same pathname
and inode with maps device `00:24` and stat device `[0,55]`. Thus attempt 02's
empty match list did **not** establish that the PE inode was absent, anonymous,
or memfd-backed; that earlier inference was unsupported. The corrected generic
predicate accepted four live Steam mappings and rejected wrong-path/inode
string fixtures before attempt 03.

Attempt 03 retained the map inode check and resolved the mapped absolute pathname
through `/proc/PID/root`, requiring its stat device/inode to equal the pinned
PE file's stat identity. Maps device is recorded as diagnostic only. The game
PID's two matching PE map rows retain inode 32667248 and maps device `00:24`;
the resolved pinned pathname has stat device `[0,55]`. Private-prefix membership,
unique selected PID, start/executable identity and connected UDP socket/fd checks
remain required. This is sampled cooperative Linux ownership evidence, not
native Win32 ownership or an adversarial security proof.

## Isolation and limits

Every attempt used a new private prefix and windowed disposable profile 45841.
The bwrap host view was read-only, with only the new run directory writable;
normal saves/settings were not selected. All three results retain confirmed
scoped cleanup, unchanged selected source hashes and unchanged Steam identities.
Attempt 03's prefix-specific shutdown left no owned groups or readable matching
prefix processes. Unreadable unrelated environments remain outside that claim.

The offer was generated locally and the save staged by Linux. No real authority
server, TLS/file-transfer session, admission, departure save or persistence cycle
was exercised. This does not validate the assembled Windows CLI, Windows ACLs,
KnownFolder handling, Win32 Jobs, native Windows, WAN or shared-world gameplay.
No player-flight/position/movement API was exercised. Initial placement and
clock-mapping decisions remain pending; no motion behavior changed.

## Private evidence

Evidence root: `.local/windows-control-proton-20261118-03/`. The exact runner is
`runner-attempt-03.py`; structured evidence is `result.json`, `control-cycle.json`
and `ownership-discovery.json`. The game log is
`compat/pfx/drive_c/users/steamuser/Documents/Egosoft/X4/45841/x4authority.log`.

| Artifact | SHA-256 |
|---|---|
| Exact attempt 03 runner | `cc6c82bb8d4c4cb9d61254664995a15230160da38bc62b439ed353afad9de6ac` |
| Run result | `a2ce2c512c1a6a9e5a954888b5581a7c4ecdac290e64449c06fbee369003acdd` |
| Game log | `4b52c9356f21831c03619a466279c060106a61d992ca877450fcfd49edb86b1c` |
| Control cycle | `9157c51bd0da74ca269aa8a85e6d3ef7004cbdeb52e842561412be0823f5c99b` |
| Ownership discovery | `a7b167c20f4383d50c14820ee2fa9b269faf6f99d32a63885e5efb4b440e430d` |

Failed evidence remains in the corresponding `-01/` and `-02/` directories,
including their exact archived runners. Device-comparison and predicate-check
records remain in attempt 02 as `readonly-steam-map-device-comparison.json` and
`readonly-mapped-image-predicate-validation.json`. No production code changed
for this follow-up and no full-suite repeat was run. Saves, DLLs and raw private
logs are not distributed.
