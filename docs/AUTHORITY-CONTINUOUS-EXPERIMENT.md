# Opt-in continuous fixture experiment

`--authority-fixture-continuous` extends the existing disposable local two-X4 fixture wire lane. It requires `--battle --authority-fixture-scan --authority-fixture-wire --authority-fixture-motion`, at least 300 ticks, and excludes the one-shot wire-warp option. It is default-off. Use only the existing isolated bundle workflow and a fresh private output. No user save or normal profile is used. The existing strict overall verdict remains authoritative.

The source estimates sector-space velocity from consecutive position samples against its own monotonic clock. Gaps below 20 ms or above one second, or rates above 5,000 m/s, produce an unknown rate instead of a zero vector. The position and any rate travel together through localhost; the receiver does not compare process clocks. Each newer packet with a finite nonzero rate predicts 100 ms ahead and writes that position using `SetObjectSectorPos`, keeping the guest's current angles. A later tick reads the same fixture. A guard pins saved fixture and sector identities and the zone ancestor, checks ship operation, player contexts and dock/storage states before writes. It cannot establish exact direct parent, atomicity or collision clearance; AI and physics can compete with corrections. The historical radians-to-degrees angle convention is not verified in this new adapter. The velocity is a finite-difference estimate, not X4 native velocity; there is no engine velocity setter. The prediction is a fixed diagnostic parameter, not an Internet latency estimate or a smoothing design. Sequence ordering does not establish end-to-end sample age; the existing relay permits stored samples up to ten seconds old.

The separate validator requires at least ten ordered writes tied to source rates with later readbacks, at least 10 m of observed guest movement, and at least five readbacks within 5 m of the target and 3 m closer than the pre-write position. It reports measured target errors. A final write at the tick limit may lack a later readback: the validator reports it separately and does not count it as observed. An intermediate missing or out-of-order readback fails. It does not prove corresponding simulation times, collision safety, physics suppression, visual smoothness, gameplay, Windows or Internet behavior. Passing is bounded evidence, not a shared-world success.

## First native observation

An isolated Linux/Linux 600-tick run combined this experiment with the
cooperative inventory. The local wire reported 571 source samples, 417 guest
receipts and approximately 2,594 m of received source movement. The guest
issued 407 corrections and made 406 later readbacks; the final correction had
no later tick and is explicitly unobserved. The scoped validator passed with
approximately 2,589 m of observed guest movement, 352 improving readbacks and
a maximum measured target error below 0.1 mm. These are local target readbacks,
not a measurement of host/guest lag, visual smoothness or native velocity.

Both cooperative inventory receipts completed at tick 70. Each recorded 203,970
list memberships for 10,070 distinct objects: 9,976 positions observed, 65 not
confirmed operational, and 29 unavailable because ship identity was missing.
The recheck was non-atomic and universe coverage remains unknown. The overall
run **failed** because the separate strict scan failed in both instances and
the gate observed divergent states. Both processes reached tick 600, restored
their hooks and exited; the checked Steam identity remained unchanged.
