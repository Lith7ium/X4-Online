# Experimental trusted-client marker load

`TrustedMarkerLoadSession` is an opt-in host-side adapter. It opens no socket,
starts no game, performs no client download or load and is not connected to a
launcher. A cooperative client may report that it requested the offered load,
observed the saved marker after the engine load event, and observed a pause.
The host can accept that report as an explicit operational assumption. This
does **not** independently prove which bytes X4 consumed, uninterrupted pause,
client authentication, content compatibility, or a consistent game world.

Construct `TrustedMarkerLoadSession(world, enabled=True)` with an exclusively
owned `WorldCoordinator`. `attach(connection)` requires a caller-owned opaque
connection object and binds it by object identity to a new coordinator handle;
the caller must establish that the object denotes the intended live connection.
The adapter cannot authenticate a network peer. `begin(connection)` checks the
confirmed version-2 checkpoint and verifies its marker in the saved MD
`X4AuthorityCheckpointMarker.MarkerState`; it returns an immutable
`MarkerBoundOffer(offer, marker)`. A different historical fixture using cue
`Store` is not interchangeable. The caller transports the offer and expected
marker to that connection and never reuses an attempt after replacement,
disconnect or restart.

`accept(connection, claim)` takes the same `HonestClientLoadClaim` type emitted
by the separate client-side experiment. It requires both claimed observations,
the saved marker, and a matching current offer, peer, epoch, handle, baseline,
generation, attempt, checkpoint ID, hash and size. It checks that the named
offer is still present in the offer service and that the same marked checkpoint
is currently confirmed. On acceptance it calls the separately named
`WorldCoordinator.mark_loaded_trusting_marker`, then consumes the attempt.
Its result says `ready_under_trusted_client_assumption=True`, while
`exact_loaded_bytes_proven` and `client_authenticated` remain false. Existing
`mark_loaded(..., trusted_confirmation=True)` retains its separate exact-byte
assertion contract. Neither method independently verifies its caller's claim.

The owner must serialize all coordinator, offer service and store operations
with adapter operations, ensure checkpoint and connection lifetime, and fence
old processes, delayed work and callbacks. The internal lock only serializes
calls to this wrapper; filesystem checks are point-in-time, not an atomic or
adversarial fence. Any possibly partial mutation faults the adapter: retire or
safely settle the coordinator and service and fence all outstanding transfers,
not merely the wrapper. A refused mismatched claim makes no state change and
cannot make another connection ready. Withdrawal cannot retract already sent
bytes. The existing shared-token file service does not supply individual
authenticated connection identity or confidentiality.

Acceptance schedules normal coordinator lifecycle work; it does not itself
perform a resume. The existing participant controller must separately confirm
pause/resume, and outstanding high-attention effects must be drained and applied
before a meaningful save. These are not solved here. The synthetic tests create
their own fake marked gzip/XML checkpoint and fake engine/service; they do not
run X4, Windows, the Internet or gameplay.
