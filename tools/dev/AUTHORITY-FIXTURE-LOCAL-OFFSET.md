# Disposable local fixture offset probe

`authority_fixture_local_offset.lua` and its separate MD cue are an opt-in
building block, installed only by the separate private diagnostic runner. They
make no network calls, accept no remote pose or handle, and do not attest
that any client and server coordinate frames agree. They are for one
**disposable, already-confirmed fixture save copy** in one private X4 process.

The private installer loads the existing
`authority_registry_resolve_string.lua`, this owner and the new MD cue in the
same process, preserve the seven saved MD scripts byte for byte, and invoke
`owner:tick()` from the existing recovery/world-bridge update owner. It must
not register another `onUpdate`. The loader must construct the owner only
once, explicitly set `enabled=true`, and pass distinct fresh 32-hex `epoch`
(the checked registry epoch) and `nonce`, slot 1 or 2, a bounded timeout, the
exact private `/45841/save` path, a trusted process/profile/checkpoint guard,
and a logging callback. The guard must prove the private owned process,
private profile and selected checkpoint remain valid. Both callbacks must be
trusted, observational, and not reenter or mutate state. The outer supervisor
must protect installed files, maintain ownership and pause, and stop on an
owner failure or incomplete/uncertain result. Loading this module alone does
not register an event or modify X4.

The MD cue checks the saved fixture slot and both directions of the four-entry
registry, epoch, owner, type, sector, direct zone parent, docking and local
player exclusion. The owner keeps actor/sector/parent handles local, repeats
FFI validity, sector/zone ancestry, ship, player, dock and exact-profile checks,
and performs two identical local position reads. It writes one +10 X-axis
sector-coordinate offset via X4's `SetObjectSectorPos`, preserving orientation
using the previously used radians-to-degrees conversion, then immediately
reads the position. A second asynchronous MD inspection verifies the same
local registry identities. The emitted coordinates are observations, not a
claim that the engine honored or sustained the write. No velocity is set.

Any failure following entry to the setter is uncertain and cannot be retried
by that owner. One construction is allowed per loaded module instance; the
installer must ensure the module is loaded only once and must never retry an
uncertain attempt by reloading it or starting another owner. The guard checks
and asynchronous MD observations are sampled, not atomic with the write.
The cue's direct-parent check can change between its event and the setter.
There is no collision-clearance proof, delayed physics observation, validated
nonzero-angle conversion, Windows result, networking or gameplay proof. The
fixture sector is intentionally restricted to the original two test sectors;
this is not a general rejoin design. No save is requested by this probe.

`tests/authority_fixture_local_offset.lua` substitutes a synthetic X4 ABI;
it verifies control flow and fences, not native behavior. The cue also passed
the local stock X4 MD schema check.

On 2026-11-17, a private, paused Linux X4 process loaded the pinned fixture
checkpoint `checkpoint-cac780ceccbd405ea367dfe028a5ae9d`. The diagnostic
selected saved registry index 4 and requested a local +10 offset on X. The
immediate readback changed from `(-56.7599983215332, 100098.7109375,
-1513.748046875)` to `(-46.7599983215332, 100098.7109375,
-1513.748046875)`, exactly the requested local position. No save was requested;
the private process and display were cleaned up and Steam identity was
unchanged. Results are in
`.local/private-fixture-local-offset-scope-real-20261117-01/`.

This proves only the immediate local position observation for this isolated
fixture and does not establish collision clearance, sustained movement,
orientation preservation, client-to-server application or gameplay.
