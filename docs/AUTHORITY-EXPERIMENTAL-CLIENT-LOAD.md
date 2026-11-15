# Experimental cooperative client load claim

`authority.experimental_client_load.ExperimentalClientLoad` is an opt-in,
transport-independent assembly helper for a single load attempt. It starts no
X4 process, issues no load or pause command, and sends nothing. A cooperative
client supervisor must serialize access and supply the events for one live
process, fresh offer and attempt. This helper is not currently wired into the
Lua load barrier, the native marker cue, a client launcher, Windows or any
transport.

The caller supplies an existing `load_messages.Offer` and the corresponding
expected checkpoint marker. It first calls `verify_staged(path)`, which hashes
the staged regular file and compares its size and SHA-256 with the offer. The
caller then invokes `observe_load_requested(attempt_id)` for the actual request,
`observe_loaded_marker(attempt_id, marker)` only when the X4 marker cue has
reported the expected marker **after** its `event_game_loaded` check, and
`observe_pause(attempt_id, True)` only after observing the same attempt's game
paused. Finally, `make_claim` rechecks the staged file and returns a one-use
`HonestClientLoadClaim`: the existing `Receipt` plus `marker`,
`load_event_observed=True` and `paused_observed=True`. Out-of-order events,
wrong attempt/marker, changed file or a failed check poison this instance;
there are no automatic retries.

These event calls are caller assertions. This helper cannot itself establish
that a real X4 process made them, that they belong to a continuous process,
that a pause persists, or that X4 read the bytes that were hashed. File
identity/digest checks are point-in-time; parent-directory races, hostile local
writers and changes between checks are not excluded. On platforms without
`O_NOFOLLOW`, the initial path check plus descriptor/path identity comparison
reduces but does not eliminate path races. The caller must own the staged
location, observe process continuity and apply deadlines/fencing. The supplied
expected marker must itself be bound to the offered checkpoint by the caller;
the current offer codec carries no marker. The host must bind the claim to the
actual current connection and reject stale session/offer/generation/attempt
before deciding whether to trust the client. A matching claim is not a security
proof and does not establish native admission or shared-world correctness.

`tests/test_authority_experimental_client_load.py` uses fake event calls and
small disposable local files; it does not execute X4 or exercise networking.
