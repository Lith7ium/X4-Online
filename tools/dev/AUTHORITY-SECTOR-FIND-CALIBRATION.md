# Saved-sector `find_sector` calibration

This opt-in, default-off experiment is a read-only diagnostic for one paused,
isolated Linux X4 process. It uses the pinned two-sector fixture checkpoint.
The existing saved-fingerprint parser independently verifies the two stored
ship and sector references, their ancestry, and the sector macro names in the
hash-checked save. The archive/load harness checks the saved marker and MD
script provenance, uses an owned process and private profile, protects its
inputs and fences cleanup. No fixture is created and no save command is issued.

After the existing load owner confirms pause and the slot-2 read, it sends one
serialized request for each saved macro and checks correlated request ID,
registry epoch, slot and macro. The new MD cue requests all matching sectors
without sorting or a result limit, requires exactly one, and compares it with
the fixture's stored local sector reference. The Lua callback independently
parses both local handles, checks equality, validates the ship and sector via
FFI and confirms their local relationship. It also checks the slot-2 handle
against the preceding local read, requires distinct sector and ship handles
across the two slots, and refuses a lost pause, changed game time, timeout,
missing/duplicate response or invalid handle. Handles never leave the local
process as network identities.

The installed game's `08.cat` contains `libraries/common.xsd` definitions for
`find_sector` (lines 28259–28281) and `findmultiple` (745–751): `multiple=true`
requests a list of found objects. The repository's prior
`native_gate_player_identity.xml` uses a dynamic macro lookup. Their combination
and the extent of this search must still be tested in X4; syntactic schema and
synthetic tests do not establish actual engine behaviour. Refusal or an X4 MD
error makes the run fail rather than creating an object or choosing a result.

Success would calibrate only the two stored fixture sectors in this one loaded
world. It would not prove general macro uniqueness, equivalent objects on a
second process, universal sector coverage, byte-exact X4 file consumption,
network delivery or shared multiplayer. The saved parser's uniqueness check is
limited to the serialized sectors in this checkpoint; it is not assumed for
other worlds or later changes. No native result is claimed yet.
