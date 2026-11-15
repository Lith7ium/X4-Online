# Disposable sector-jobs observation probe

`authority_sector_jobs_probe.xml` is a default-off MD component, not installed
or run by itself. It has no runner and has not been exercised in X4. Use only
in an independently isolated disposable profile, never a normal save. It
neither creates ships nor sends orders, changes positions, or resets permissions.
Control and treatment must load separate copies of the same confirmed marked
checkpoint; discard both copies afterward.

The checkpoint must contain initialized `X4AuthorityShipRegistry` and
`X4AuthoritySectorReferenceFixture` state, including the fixture's first
existing ship and sector. A future supervisor must establish the checkpoint,
epoch and process identity, serialize this probe's events and operations,
confirm pause independently before and after each request, impose a timeout,
and discard the case on refusal, MD error, silence or uncertain delivery. This
probe cannot verify pause or process identity, prove its host used a disposable
profile, or establish that checkpoint copies are identical. Responses carry no
request ID or epoch, so the supervisor must own the callbacks exclusively,
serialize requests and fence late responses. A refusal does not permanently fault
the cue: the caller must abort and discard the case on every refusal or timeout,
even if the cue might respond to a later request. The `State` cue is one-shot;
never automatically retry `Begin` after a missing or uncertain response.
Request `Begin` exactly once on screen `X4AuthoritySectorJobsProbe` with table fields
`epoch` and `mode`, the latter exactly `control` or `treatment`. The cue checks
the fixture/registry epoch, both registry mappings, ship/sector binding,
operational ship, non-player status, a pilot and the current order's reported
type and `started` or `critical` state at that sample. The treatment alone sets jobs permission false for that
saved sector; control does not change it. `Began(order_id)` follows these checks
and the optional action. It is not proof of the effective sector permissions,
their child overrides, or that the setting affected the ship.

With the same epoch, send `Sample` while independently confirmed paused after
the observation interval. `Sampled(order_id)` means the same saved ship,
sector, registry mappings and pilot still pass the checks, and the current
order reports the same type ID and one of the two stated states at this sample.
This does not identify the same order instance: one order may have ended and
another of the same type may have started between the samples. A different pilot,
missing/changed reference or order type, faulted registry or wrong epoch causes
`Refused` when the cue reaches its explicit error branch. Treat missing replies
or MD errors the same way; the probe itself does not latch every failure.
`Refused` is inconclusive and is not evidence that jobs or simulation were
suppressed. These samples establish neither continuous operation nor the ship's
job membership, motion, or the cause of motion. This component does not
measure time, position, velocity, ship creation or events. In particular, `Sampled`
is not evidence by itself that the ship continued to act after treatment.

For a meaningful comparison, a separate read-only observation must establish
actual behavior during the interval and distinguish it from inertia or other
causes; a stopped or missing order alone does not establish a general rule.
No inference can be made about God, faction logic, unobserved sectors, child
permissions or creation paths. A short test with no observed behavior remains
inconclusive. The schema documents the permission setter and order states.
Vanilla `08.cat/md/conversations.xml` uses the `ship.order.state` expression;
the native NPC-flight fixture separately exercised `ship.pilot` and
`ship.order.id` on a controlled ship. This exact cue, state expression on the
selected saved NPC, refusal paths and treatment effect are not yet verified in
native X4. Structural tests execute no MD expressions and do not prove them.
