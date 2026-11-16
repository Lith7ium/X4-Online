# Read-only local player-flight observer

This default-off test component observes one already confirmed player-controlled
fixture in one private X4 process. It installs no event handlers or `onUpdate`,
and never sends keyboard/mouse input, calls `Pause`/`Unpause`, writes position
or velocity, creates ships, saves, or transports data. Its caller owns the
existing update loop, event routing, actual resume, any separate input helper,
process ownership, safe private profile and all cleanup. It is not a native
runner or a player-control implementation.

The exclusive caller must first have completed the guarded control-once
experiment and independently verified both positive control readbacks. MD's
`State.$next == 3` alone says only that the prior read events were issued; it
does not attest their contents. The owner supplies the already verified target,
sector and direct zone-parent as exact process-local uint64 values, the observed
owner ID, a fresh epoch/nonce, a positive `confirmed` callback and its own
external process/file/deadline guard. No local component ID is returned in the
observer's result or suitable for network use.

1. `arm()` requires a paused player still occupying and controlling that exact
   operational player-faction ship in the same target sector and zone-parent.
2. `begin_resume()` records an explicit boundary while still paused. The owner
   may then request resume through its own independently guarded mechanism.
   `tick()` waits for an unpaused state and observed game time strictly greater
   than the paused baseline. Failure to observe progression is not success.
3. In order, the owner calls `request('neutral')`, `request('before')`, and
   `request('after')`. Each request is one-shot and serialized; the owner
   routes its matching MD Result (or Refused) into the observer. The observer
   checks epoch, nonce, sequence, local target/sector/zone, MD player-control
   and owner conditions and the independent UI/FFI identities and owner. It
   samples finite sector-position and yaw/pitch/roll values bracketed by real
   and game times, and checks the same binding again. Each successive sample
   must start after the prior sample ended in both observed real and game time.
4. After the third response the owner must continue checking the observer and
   callbacks until it deliberately closes and safely stops the private process.
   Late, duplicate or out-of-order events, a missing/invalid getter, an identity
   or owner change, renewed pause, time regression or deadline cause a fault;
   requests are never retried automatically.

Sample labels describe only the caller's order. They do not establish that a
neutral input state existed, that an input was injected or reached X4, or that
input caused any position change. The UI pose and rotations are native readbacks
in the tested sector context; this component does not establish angle units,
coordinate transformations, native velocity, continuous collision clearance,
shared simulation, Windows/Internet operation or gameplay. The MD and FFI
reads are sequential point observations, not an atomic world snapshot.
`movement_cause_proven`, `input_proven` and `multiplayer_proven` remain false.
Synthetic Lua/FFI and X4 schema tests do not prove native behavior. The fake
X4 fixture exercises an exact ID above 2^53, but is not evidence for the real
engine's ID or event serialization. No native flight observation follows from
installing or testing these files.
