# Experimental session position rates

`experimental_motion_rates.py` is a pure, in-process adapter for an existing
`ShipRegistry`. It accepts complete positions and a **source monotonic clock in
seconds** supplied by a trusted caller. The finite-difference vector is expressed
in the position frame's coordinate units per source second. It is a derived rate,
not a native X4 velocity, an authenticated message, or evidence of smooth motion.
The caller must establish that all samples in one ship generation and authority
epoch use the same physical clock and that each frame token means the same
coordinate frame. The adapter does not validate game actors or sectors.

For each bounded per-ship history, the first sample and a new generation,
authority epoch, owner, frame, or an excessive time gap produce an unknown rate.
Too-short intervals preserve the earlier reference but emit an unknown rate;
reordered sequences and regressing source time are rejected. Excessive or
nonfinite differences also emit unknown and start a new reference. Unknown clears
any previous velocity on the registry state. An unchanged position with a valid
interval yields a known zero rate.

Registry rejection cannot advance rate history. A foreign registry update in the
same lineage is detected using the exact previously returned immutable state;
the caller must explicitly `forget(ship_id)` before treating a later sample as a
new reference. This check currently relies on the registry's private `_current`
method and is not a stable public API. Callers must serialize all access. A new
world/session requires a new registry and adapter; `forget` only removes local
rate history and does not remove a ship.

The prior natural-flight test used a finite-difference rate for one fixture in a
terminal, isolated Linux/Linux harness. Its local fixture datagrams do not carry
an authenticated session identity or the source timestamp that this adapter
requires, and the guest writer was pause-guarded. This module is not wired to
that experiment, does not change its native result, and does not establish a
reusable multi-client transport, session admission, common sector identity,
collision safety, universe coverage, or live gameplay. A future integration must
provide those properties and independently validate source identity and clock
semantics before calling this adapter; remote timestamps cannot simply be
compared to a recipient's monotonic clock.

Run `python -m unittest discover -s tests -p test_authority_experimental_motion_rates.py -v`
for focused synthetic checks; no game or network is started.
