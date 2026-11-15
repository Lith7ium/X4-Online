# Isolated fixture pose adapter

`src/authority/lua/x4_fixture_pose_adapter.lua` is a default-off, one-shot
primitive around the mock-tested `pose_apply.lua` guard. It is not registered
with the UI or runner and must not be used in a normal game profile. It binds
only locally supplied fixture 1 and its locally supplied sector; network data
cannot select an object. There is no deletion, activation, velocity setter,
cross-sector warp, scheduler, or multiplayer integration.

The adapter checks an explicit guest-test option, the pinned snapshot hash and
saved fixture/sector identities, a private profile path, a stable zone,
operational and ship flags, local player controlled/occupied/containing ship,
the three native docking flags, and absence of an enclosing container. It
rechecks these gates around the independently supplied clearance check. One
attempt, between 5 and 50 metres, is allowed by the existing wrapper, followed
by an immediate readback; failures remain failures. An exception after entering
the setter wrapper is conservatively reported as an attempted write even if a
later guard prevented the native setter from executing.

This module is **not cleared for a native run**. A trusted harness must first
implement and validate all four mandatory attestations:

1. The exact private process is using the supplied private save directory and
   has actually loaded the pinned disposable snapshot; a profile suffix or
   configuration string alone is not proof.
2. The fixture's direct native parent is the enrolled zone. A nearest-zone
   lookup establishes an ancestor, not the exact parent.
3. The fixture contains no other player representation, including passengers
   not represented by the local player's three native context queries.
4. The proposed destination has safe physical clearance for the complete
   fixture; this must be an independent current-world observation.

The historical getter-radians/setter-degrees convention is also unverified for
this new native adapter and requires a nonzero-angle control. The guards are
not atomic with the native write: object lifetime, containment, player state,
collision clearance or concurrent AI/physics can change between observations
and the setter. Immediate readback does not prove the position remains stable,
that AI/physics are suppressed, or that an enclosed child follows correctly.
The existing proposed control matrix in `AUTHORITY-INVESTIGATION.md` remains
necessary. Tests for this adapter use injected mock bindings and attestations;
they do not establish native safety, synchronization, or gameplay.
