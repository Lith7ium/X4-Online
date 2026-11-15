# Registry-to-motion diagnostic

`authority_registry_motion_probe.lua` connects a locally resolved `(epoch,
index)` to existing one-fixture loopback wire and position-prediction modules.
The separate `--motion` option of `authority_create_test_live.py` prepares a
native two-instance test with disposable profiles. It is not a gameplay client, lifecycle monitor, or
universe-wide replication.

The test initializes one ship through the existing creation/registry fixture.
Each sample first requests `X4AuthorityRegistryMotionGuard.Validate`, which
checks the saved forward and reverse references, frame, direct zone parent,
player context and docking state in MD. Only one such request may be pending:
the response does not identify its request. The Lua native binding then checks
that X4 is paused, the exact private save path and locally pinned actor, sector and zone, as well
as component lifetime, player context and docking state. A failed check stops
the adapter. The pause state is also checked before each guard request and
immediately before either test setter; losing pause or another error latches
failure and late guard responses are ignored. A fake-symbol LuaJIT test covers
pause loss; the X4 runtime behavior remains unverified. There is a gap between the MD check and native calls; no atomicity
or independent collision-clearance proof is claimed. This test must never be
used with normal saves, player ships or an assumed clear area.

The local wire fixture label contains epoch, index and the expected sector
macro. The test compares the source and guest sector before starting the relay.
This is a fixed same-sector fixture, not a proven universe-wide sector identity
scheme. Unknown rate causes no guest write; a known zero rate is accepted.
Position is sector-relative metres. The monotonic clock returns seconds, and
velocity is a source position finite difference in metres/second. The receiver
uses the existing diagnostic to predict 0.1 seconds and invokes a native
**position setter**, not a native velocity setter.

The source fixture receives at most twenty controlled 5 m setter impulses while
both instances are paused. These impulses are not NPC flight. The native test
uses a disposable profile, but the coordinates are not independently proved
collision-free. An evidence checker verifies matching source sequences,
position/rate, prediction, and guest readbacks; this does not demonstrate
visually smooth movement, angular velocity, gameplay, native velocity sampling,
Internet or Windows operation. `FixtureUDP` is limited to localhost and one
fixture. Native setter angles and non-atomic guard behavior still need native
verification on the targeted executable.

One isolated Linux/Linux X4 run passed the diagnostic: the checker recorded
970 source samples, 34 guest writes, 33 matching guest readbacks, and 20
controlled source setter impulses. The one ship was created after the common
checkpoint and resolved under the same registry index in both paused instances;
the rate was derived from positions, not read from native velocity. The result
also records that exact loaded bytes were not proved and no client was admitted.
This observation does not establish NPC flight, collision clearance, atomicity,
smoothness, gameplay, or Windows/internet operation.

`tests/authority_registry_motion_probe.lua` exercises the real Lua wire and
motion modules with in-memory transports, fake clocks, fake registry and fake
writer. It is not an X4 test. The source is enabled only through the explicit
runner flag; imports and normal creation tests do not launch X4 or enable motion.
