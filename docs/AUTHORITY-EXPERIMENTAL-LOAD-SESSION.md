# Experimental load attempts

`authority.experimental_load_session.ExperimentalLoadSession` is a small,
transport-free experiment over one existing `WorldCoordinator`, `SaveOffers`
and the experimental `load_messages` values. It starts no engine or network
listener, loads no save and does not admit a client. Revoking an offer can
interrupt transfers already active in the separately supplied service. Its only receipt
method is explicitly named `observe_test_receipt`: success means that synthetic
fields matched the then-current in-memory offer and session. The returned
observation sets `native_load_proven`, `authenticated` and `admitted` to false.
It never calls `mark_loaded`, `mark_ready` or sets `trusted_confirmation`.

The caller supplies peer labels and must serialize **all** access to the
adapter, coordinator, session, offer service and their lifecycle. A label is
not an authenticated transport identity; a receipt's handle does not identify
its sender. Each attachment receives a coordinator handle; each new attempt
has a fresh attempt ID and the coordinator's new load generation. An
observation compares the caller's peer, epoch, handle, baseline, generation,
attempt, checkpoint ID, SHA-256 and size with the adapter's current offer and
coordinator state, and requires the offer still be present in both SaveOffers
and the local service. A successful synthetic observation withdraws the offer
and cannot be repeated. Disconnect, replacement or revocation makes an old
receipt unusable in this adapter. The offered name is checked locally; the
existing receipt does not bind a name.

This is not an atomic, adversarial or interprocess fence. Independent direct
changes to the coordinator or service, including withdrawal followed by
re-insertion between checks, are outside its exclusive-owner contract. The
caller must use a fresh coordinator epoch after restart. Attempt IDs are
randomly generated and checked for reuse within this adapter; they are not a
new authentication or cryptographic security scheme. The shared-token
join-file service does not bind an offer to a particular peer or slot and does
not provide confidentiality. Already delivered bytes cannot be revoked.

The codec has stricter bounds than the coordinator (including 2^53−1 for
integer fields); these are checked before starting a load attempt. An error
during join, disconnect, offer creation or receipt consumption may leave
coordinator state or the service partially changed. The adapter permanently
faults and makes no rollback claim; it does not automatically revoke every
other peer's offer. The owner must fence all outstanding transfers and discard
or otherwise safely settle the service and coordinator before continuing.
Simply creating another adapter is not recovery, and no automatic retry is
safe.

`WorldCoordinator` does not currently drain, fence or apply outstanding
high-attention results before saving. A synthetically correct session or
checkpoint sequence therefore does not establish a consistent game state.
Real process identity, actual X4 loading, authenticated peer binding, durable
checkpoint freshness and remote network operation remain separate work. Most
tests use a fake engine and fake in-memory service. One focused integration
test uses the actual FileService on an ephemeral `127.0.0.1` port, a fake
engine and a disposable checkpoint: it round-trips the offer codec, transfers
and hashes the save, consumes a synthetic receipt and checks that a subsequent
fetch is refused after withdrawal. It closes and joins its owned server. This
local test establishes neither X4 load/admission nor Windows, WAN, peer
authentication, confidentiality or other security properties.

`tests/test_authority_loopback_lifecycle.py` adds a separate real-loopback
exercise with three labelled fake players, a fake engine and fake participant
controls. The test explicitly calls `WorldCoordinator.mark_loaded` with
`trusted_confirmation=True` as a **test assumption**, without invoking
`observe_test_receipt` to authorize anyone. After two fake players disconnect,
the third advances a fake counter, disconnects, and causes fake pause/save;
later, a new attachment downloads the resulting confirmed checkpoint over TCP.
An independent counterexample consumes `observe_test_receipt` and verifies that
no player becomes ready or causes a resume or unnecessary last-disconnect save.
The fake confirmation bypasses this experimental adapter's non-admitting API;
its stale adapter attempt is rejected when observed afterward. This test does
not establish real admission, X4 execution, remote networking, or recovery after
a server-process restart. Reopening `CheckpointStore` validates access to the
fake checkpoint, not restoration of a running world.
