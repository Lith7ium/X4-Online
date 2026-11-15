# Opt-in local wire-to-warp experiment

This diagnostic adds one guest write to the disposable, two-Linux fixture
wire lane. It is not integrated into multiplayer or production. Its source uses
the existing movement order only in p1; p2 receives a sector-space coordinate
through the existing IPv4 loopback fixture adapter. Once a received point lies
at least 10 m from the guest fixture, p2 issues exactly one MD warp. A cue
acknowledgment is recorded as an acknowledgment, not as completion. At least
one real monotonic second later, the guest reads the fixture position again.
The separate validator requires this to be within 3 m of the exact unique
received/source packet. It also checks pre-write separation and both sides'
fixture and sector saved-identity digests, whose underlying IDs were derived
from the same snapshot during bundle creation. Runtime guards repeat identity,
sector, parent zone, operational, local player, docking and storage checks.
Raw identifiers and coordinates remain in the private bundle/run evidence.

Build requires the existing disposable Linux bundle workflow, `--battle`,
`--authority-fixture-scan --authority-fixture-wire --authority-fixture-motion
--authority-fixture-wire-warp` and at least 300 ticks. This flag is default-off.
The runner's original strict overall verdict remains unchanged: a digest split
is observed, and a divergent gate result remains a failed overall test even if
the separately reported `authority_wire_warp_evidence` passes. Use a fresh
private output, the same isolated profiles and cleanup as the existing lane.

This experiment tests one delayed, network-sourced position, not continuous
replication, another sector, high-attention handoff, velocity, Internet,
Windows, persistence, collision freedom, atomicity, or gameplay. A moving
source and receiver are not compared as concurrent world states. No native
result is claimed until the full log and cleanup have been reviewed.

## First native attempt

In one isolated Linux/Linux attempt, both processes reported a generic wire
probe error before any source sample, guest receipt, or apply request. The
supervisor was asked to cancel once that failure was observed; its result and
the scoped evidence both failed. Owned X4 processes exited and the checked Steam
identity remained unchanged. This attempt provides no evidence that a received
position was applied. The probe was changed to report fixed, non-identifying
failure stages and to pass exactly one argument to the component-ID conversion.
The original failure's precise cause was not established.

## Second native attempt

In a fresh isolated Linux/Linux run, source and guest enrolled the same saved
fixture and sector and the source moved the fixture. The source sent 331
samples and the guest received 241; the wire validator observed about 1,290 m
of received movement. The guest's one-shot request was tied to a unique received
source sample about 10.25 m from its pre-write position. The delayed readback,
1.37 real seconds after acknowledgment, matched the requested position to the
reported precision. The separate one-fixture wire-to-warp evidence passed.

The complete run **failed**: the strict fleet scan produced no passing receipt
in either instance, and the relay reported a divergence as expected with the
source-only movement. Both instances reached their 360-tick stop and restored
their hooks. The owned processes exited and the checked Steam identity was
unchanged. This is one application, not continuous position replication,
velocity smoothing, another sector, Internet or Windows behavior, or gameplay.
