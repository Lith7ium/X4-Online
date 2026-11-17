# Fixture player pose: offline one-shot contract

`lua/fixture_player_pose_once.lua` is disabled unless explicitly enabled. It
has no native bindings, game registration, socket, scheduler or integration
with the server. It does not call an X4 setter by itself. The caller supplies
all callbacks, including the writer, and owns the real X4 process and failures.
The supplied test writer only changes an in-memory counter.

The grant fixes registry index 3 or 4, source, epoch, generation, exact
sequence, sector and frame token. The input pose uses sector coordinates and
radians. Before the single permitted write, the owner requires two identical
local actor/sector/parent and player-context observations, no docking or
storage, and explicit attestations of the granted source-to-local frame.
It repeats these observations after the writer returns. A callback must return
exactly `true`; local object references never need to cross the network.
Any failure after entering the writer is `uncertain` and is never retried.
This one-attempt rule applies only to one owner instance. Creating a second
instance for the same grant would allow another attempt. Any future integrator
must enforce replay protection across instances for each granted source,
generation and sequence, including after uncertain outcomes.

Matching a sector name, frame token, registry index or copied save does **not**
establish equal coordinate frames. `frame_attested` is an external assertion,
not proof. No real writer may be wired or called until the surrounding native
experiment has independently established the exact local identity, physical
frame equivalence and lifecycle guards. Checks are sampled, not atomic with a
game write; this module does not prove clearance, physics stability, native
velocity, continuous control, multiplayer or persistence. A future native
adapter must convert angles correctly for its X4 API and resolve local handles
itself. The owner never sets native linear or angular velocity.

`tests/authority_fixture_player_pose_once.lua` exercises the owner with
simulated objects, including missing attestations, changed identities,
player occupancy, writer failure and reentry. It is not a native X4 test.
