# Paused saved-sector frame comparison

On 2026-11-16 the isolated diagnostic `.local/authority-saved-frame-pair-01`
reported `success=true` and confirmed cleanup with no owned processes
remaining. Two Linux X4 processes were started with separate private profiles
and read-only staged copies of the pinned census checkpoint. Each logged the
expected load marker and an observed pause before its frame rows. The staged
save copies both had SHA-256
`64a233ac6a85194b8276212709e78a6c48bbcc0f73c19842622aa098f1408cb8`.
This does not independently prove which file X4 consumed.

The opt-in local MD/Lua probe looked up saved ship registry index 1318 in
`cluster_115_sector001_macro` and the eleven saved station codes identified in
the pinned checkpoint. It checked local registry and sector relationships,
operational components, and local ID-code, macro and faction values. Each
position was read twice with pause and game-time guards; actor and sector
handles remained in their respective X4 processes. The source and client logs
used distinct request nonces. Their rows and DONE markers each reported local
game time 3.037; this is not a synchronized-clock assertion.

Both logs reported ship code `WRG-830`, macro `ship_ter_m_corvette_01_a_macro`,
faction `pioneers` and position `(-131813.265625, 1456.1710205078125,
-44963.94140625)`. All eleven common station codes had matching local macro
`station_gen_factory_base_01_macro`, faction `pioneers` and matching reported
positions. The independent comparison of the two logs found a maximum station
position delta of 0 and a ship delta of 0. The predeclared acceptance limit was
one local coordinate unit; it required at least three shared station anchors
with arms of at least 1000 units and a sine of at least 0.05 in both processes.
The result identified eleven common codes:

`AAJ-808`, `LMC-637`, `LOO-275`, `ODV-102`, `OKE-308`, `RZT-476`, `SJE-557`,
`SUM-216`, `UJU-480`, `UKN-243`, `UTM-602`.

The probe MD and Lua files installed in both private profiles had SHA-256
`9fad89bee7de3f08afb169ef4a24bb3b05a07345a931cf573b9691d27269889e` and
`593c226e2be1757d2c4930e4c55213a1b0edbdb1da707f67e9aa689616b8171e`
respectively, matching the reviewed source files. The result reports owned
process cleanup; no raw PID/inode trace or complete overlay audit was retained.
The pinned-save, script and process protections are checked by the runner, and
pause/identity are sampled rather than atomic guarantees.

This is evidence of matching reported coordinates for these anchors in this
one paused Linux/Linux test. Matching labels and sampled coordinates do not
prove cross-process actor identity, a shared checkpoint, universal coordinate
frame identity, continuous pause, compatibility after resume or between other
sectors, or correctness of a position/velocity setter. It does not demonstrate
interest subscriptions, visible movement, Windows, Internet or gameplay.

The installer and comparator are `authority_saved_frame_pair_live.py` and
`authority_saved_frame_compare.py`; the local probe is
`authority_frame_read.lua`/`.xml`. Their focused tests simulate X4 and MD;
the native observations above are a separate bounded run.

## Optional current-registry compatibility diagnostic

The default-off `--diagnostic-current-registry-script`, together with the
required explicit `--expected-current-registry-sha256`, installs the current
`authority_ship_registry.xml` in each disposable profile over a staged copy of
the pinned census checkpoint. This deliberate overlay differs from the script
that was saved with that checkpoint. The archive's own provenance and original
scripts are checked as before; only this one private overlay is checked against
the separately pinned current source. Before process launch the source hash
must match the explicitly supplied value. The other saved-state overlays must
still match the archive. The archive scripts are checked against their expected
versions during profile preparation; the running archive fingerprint does not
cover those scripts. The current source and installed files are fingerprinted
and sampled during the diagnostic. The expected ship code, macro and faction
are required independently in both parsed frame observations.

The frame probe reads the existing registry state directly; it does not issue
the current script's correlated status request. Consequently, this experiment
does not prove that the new registry cue actions executed, that all saved
references or generations survived a save/reload, or that this checkpoint is
accepted by the separate witness-recovery supervisor. No checkpoint is saved
or confirmed. The existing checks for the archive, private processes, pause,
marker and staged files continue to apply. This option has focused offline
tests as well as the single native observation below.

The isolated Linux/Linux run `.local/authority-current-registry-frame-01`
reported success with current script SHA-256
`b39c8cfad274f74411cd2b518976f7d343c9c43666d8c9a8a8dc62b55443b0af`.
Both logs recorded the saved marker and a pause observation before reporting
the expected ship code, macro and faction at registry index 1318 in the
expected sector. The comparator reported zero position difference for the ship
and eleven shared station anchors, within its one-unit tolerance. The result
reported no remaining owned processes and confirmed owned-process cleanup.
The logs also contain read-only configuration-write errors, unavailable FSR3G
queues and a missing extension signature; the run's success concerns only its
stated load and frame checks.

This is a point-in-time observation with the current script provided in the
private overlays. It does not establish that the current script's changed cue
actions executed, that X4 consumed the exact staged file, or that the two
reported ships are independently proven to be the same runtime actor. It does
not demonstrate a recovered multiplayer session, movement, Windows or Internet
operation, or a successful new checkpoint.
