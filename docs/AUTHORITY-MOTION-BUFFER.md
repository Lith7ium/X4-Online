# Read-only authority motion buffer

`src/authority/lua/motion_buffer.lua` is an isolated reconstruction experiment. It is adapted from the previous LAN experiment's original `extension/x4_lan_lab/ui/motion.lua`: source-clock mapping, bounded sample buffers, wrapped Euler interpolation, constant-rate extrapolation, discontinuity detection and the clock-offset leak retain that design. It makes no X4 calls and is not wired into the diagnostic fleet, a game object, a native velocity setter, or an Internet protocol. The previous LAN native results do not validate this adaptation in X4.

## Input and output

Create one `motion.new(options)` track for **one already identified object and one continuous source/session**. Supply the following to `track:push(sample, arrival)`, where `arrival` is a nonnegative, monotonic observer clock in seconds:

```lua
local accepted, reason = track:push({
  frame = 'agreed-frame-token', sequence = 1, source_time = 42.0,
  pose = {x, y, z, yaw, pitch, roll},
  rate = {vx, vy, vz, yaw_rate, pitch_rate, roll_rate}, -- or nil
}, arrival)
local result, error = track:render(now)
```

The caller must establish what a frame token means and ensure pose, velocity and frame really agree between producers and consumers. Changing frame clears earlier samples; no coordinate conversion is performed. A fresh track is required for a source, authority, object-lifetime, process or session change. Angles are radians and angular rates are wrapped **Euler-coordinate derivatives**, not native angular-velocity vectors. XYZ is expected in metres and translational rate in metres/second only when the caller's frame has those units. Rates may be absent; the renderer holds the last pose instead of inventing zero or a movement vector. No native velocity setter is called.

`motion.estimate(previous, sample, max_gap)` can derive six rates from two validated samples with increasing source time and sequence in the same frame. It returns nil for missing/invalid data, frame changes, too-small or excessive time gaps, or out-of-bounds rates. Callers must avoid deriving a rate across a teleport, lifecycle or authority transition; this helper cannot recognize semantic object replacement. Identical poses produce a real zero rate.

Push rejects invalid or nonfinite fields, stale sequence/source time, or a backwards observer time. After frame change, a source gap over the configured stale threshold, or a displacement beyond the configured limit plus the **previous** speed times elapsed time, it drops earlier samples and discards the new sample's rate until the next update. The discontinuity limit is a heuristic, not proof that teleportation did or did not occur. Accepted input is copied; at most sixteen samples are retained.

Rendering maps observer time to source time using the lowest observed offset, with a bounded rate of offset increase to accommodate drift. It interpolates between known samples (using shortest-angle wrap). Beyond the latest sample, it applies the supplied linear/Euler rates up to a configured horizon, then freezes at that predicted pose. If the pose would exceed validation limits, rendering fails closed. `result.phase` is `held`, `held-no-rate`, `interpolated`, `extrapolated` or `frozen`. The result freezes indefinitely once its horizon is reached; the caller is responsible for expiring, hiding or replacing stale objects. Arrival/clock data do not prove actual capture time or provide synchronized clocks.

Defaults mirror the earlier normal-flight LAN buffer: 0.15 s delay, 0.35 s prediction horizon, 0.75 s stale gap, 10,000 m discontinuity base, 0.002 s/s clock-offset leak and 0.1 s/s render-clock slew. They are adjustable test parameters, not production tuning or evidence of smooth gameplay. For large offset jumps the render clock can snap, as in the source experiment. This adaptation does **not** include the LAN experiment's adaptive delay, per-mode high-speed thresholds, velocity fences, native lifecycle logic or NPC prioritization.

`tests/test_authority_motion.py` uses LuaJIT without X4 to check irregular samples, bounded extrapolation and freeze, coordinate-frame change, teleport, gap, angle wrap, stationary data, absent rates, invalid data and reordered input. The tests do not establish visual smoothness, high-speed behavior, accuracy in X4, collision correctness or Windows/Internet behavior.
