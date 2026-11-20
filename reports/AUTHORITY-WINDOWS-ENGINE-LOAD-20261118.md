# Windows engine checkpoint load under Proton

The Windows X4 executable loaded the existing Linux-produced checkpoint and
emitted the expected marker, two identity-fixture observations, registry header
and pause receipt. This bounded engine-load diagnostic passed after fixing the
Windows overlay's marker script. It is not a native Windows or multiplayer test.

## Failure and correction

The first run reached both save-loading passes, then reported
`AUTH_MARKER load ERROR` at the existing 60-second observation deadline.
The Windows builder installed `tools/dev/authority_checkpoint_marker.xml`,
whose inspection reads `Store.$marker`. The offered checkpoint instead stores
its marker in `MarkerState.$marker`. The successful Linux recovered-client
path already installs `src/authority/md/checkpoint_marker.xml`.

The Windows overlay now installs that same persistent marker definition.
No deadline, admission requirement, pause behavior or motion setting changed.
An installed-overlay regression checks the persisted state namespace and its
load-event/inspection contract; it failed with the old source selection.
The 17 targeted overlay, marker-probe and marker-evidence tests passed with no
skips. The full suite was not repeated.

## Observations after the fix

One follow-up used a fresh private Proton prefix and profile 45841, the same
checkpoint and DLL, and the same startup/load limits. The log records:

- An attempt-correlated request for `save_009`, followed by both load passes.
- The expected marker `68b10a9b6689f327940935648f726db7` read from the world;
  the expected value was not injected into the Lua configuration.
- Both named identity ships, `alpha 7181` and `beta 7182`, with their expected
  `ship_arg_s_fighter_01_a_macro`, followed by `AUTH_IDENTITY load READY`.
- Registry epoch `4ba7be438ebb04ec5bb85fdb95b5a488` and count **10,082**,
  correlated with a fresh inspection nonce.
- The matching `pause_observed` receipt, in the required sequence.

The supervisor returned `engine_load_observed`, exit zero. Both runs recorded
unchanged input hashes and Steam process identities. Prefix-specific wineserver
shutdown/wait succeeded; no owned groups or readable matching-prefix processes
remained, and a subsequent process-name check found no X4. Five unrelated
same-user environments were unreadable; this is scoped cleanup evidence, not
a proof about every system process. No normal profile was selected. The host
filesystem was mounted read-only inside bwrap, with only the new run directory
writable. Each client ran windowed, alone, using GE-Proton10-29 and the installed
Windows X4 9.00 (611726) depot plus Linux game data.

## Scope and artifacts

The load offer was generated locally by the diagnostic; no authority server,
TLS/file transfer or admission session ran. Linux prepared and owned the
filesystem/processes. Windows ACLs, KnownFolder resolution, Win32 Jobs and the
assembled Windows fixture CLI were not exercised. The live registry receipt
checks its header, not every runtime ship mapping. No movement, player controls,
trade, combat, boarding, persistence cycle or Internet connection was tested.
This does not resolve the separate initial-position/clock decisions.

Private reproducer: `.local/authority_windows_x4_load_proton_20261118.py`, SHA-256
`e050df20d35d7f158fcdee2dbb17ab782d1036e591ac8de95c8c3f30ca0a4e8d`.
It uses the existing Proton isolation helpers and the tracked Windows overlay.
The failed and corrected runs are `.local/windows-x4-load-proton-20261118-01`
and `-02`, respectively. Each contains `result.json`, launch/proton logs and
`compat/pfx/drive_c/users/steamuser/Documents/Egosoft/X4/45841/x4authority.log`.
The first result remains failed.

| Artifact | SHA-256 |
|---|---|
| Checkpoint `save.xml.gz` | `2ebbcea67f4993c8da7f93661779ca8f3a9539d1f59a865ca811b71f852e7af0` |
| Windows X4 executable | `19750a6563889a970f434b5566eb396c6b2dc29ff814bd3e336f838176ad6891` |
| Windows network DLL | `6ad97e04fd804c031b673af7259e4010b0afb2ad095e8821647998a69e2809e0` |
| Failed run result | `25af572a5a5a17fa1fb66578985d39906005b6e7e4e5a26d1150e18b5d29994c` |
| Corrected run result | `9ade56f34b6d4c57b48af879d5ed6841ed57dbc1ed0ba9fcb7f8dab84a06d944` |
| Corrected game log | `abc4bedacc6b7dd9b63ec4cb924f515cf88bcf7e2e7e27eb80c1b6112ea7f426` |

The checkpoint is native05's `checkpoint-24446e8b364c49289b953ff0aca58470`.
All game files and checkpoints remain private and are not distributed.

## Full-registry checkpoint load, 20 November 2026

The Windows executable ran under Proton on an isolated X11 display, using a
new prefix and disposable profile for each attempt. The input was slot 010
from the [Linux two-save test](../tools/dev/AUTHORITY-REGISTRY-CHECKPOINT.md),
with 10,082 issued entries, a verified MD marker and a matching source registry.
The load controller staged it in client slot 009.

The first attempt recognized the marker and both fixture ships, then refused
readiness because an inspection vector differed. X4 also logged 32 failed
imports of saved faction values. The Windows fixture lacked the faction and
icon libraries and 16 textures that the Linux producer had loaded. Including
the identical tracked assets removed those import errors. Company membership
and ship ownership require no reassignment.

The second attempt at `2a04cdbc` still refused readiness. The saved and
live binding flags agreed at every index, as did the saved operational flags.
Only the live operational flag of index 4015 differed, from 1 to 0.
In the input save this index refers to `MWQ-670`, a Xenon M corvette in
`cluster_405_sector001_macro`, with a temporary attack order and a recorded
attack at game time 53.148. The cause of the operational change was not recorded.
Linux had saved at game time 54.073. The Windows process logged the refusal
at 54.63. The client previously requested its pause after marker and fixture
checks. At `df220f90` it requests pause on the first playable frame and
holds it while those checks run.

The third attempt at `df220f90` passed on the same input. X4 reported the
marker, both named ships, the full inspection of 10,082 entries, the registry
header and the pause at logged game time 54.07. All four vectors agreed,
including the live operational flag of ship 4015. The runner confirmed
cleanup and unchanged inputs and Steam identity. Its log SHA-256 is
`4b218d53f2a42cc6f3d21789ea5a0dc1cd0c82b29cd50a9b2078fdf2267248da`.
This was a local engine load under Proton. No participant connected to a
server in this test.

Private evidence is under `.local/windows-snapshot-load-proton-20261120-01/`
and sibling runs `-02/` and `-03/`. The first two attempts ended with verified owned-process cleanup,
unchanged input digests and unchanged Steam process identity. Neither attempt
issued an admission claim.
