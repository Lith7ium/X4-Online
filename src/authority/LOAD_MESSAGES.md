# Experimental load-message codec

`load_messages.py` encodes an existing checkpoint offer or a description of a
load attempt as bounded version-1 UTF-8 JSON bytes. This is an experimental,
transport-independent data format; it is not wired to a network, launcher,
X4, or the coordinator's admission path. It opens no sockets and does not
choose an authentication, encryption, session, or authority mechanism.

`from_load_offer(coordinator_offer, attempt_id)` copies the existing
`WorldCoordinator` offer and accepts a 32-character lowercase-hex attempt ID.
The caller must generate a fresh ID; this function cannot check freshness.
`encode_offer`/`decode_offer` operate on `Offer`; their receipt
equivalents operate on `Receipt`. An offer carries world epoch, connection,
baseline and load-generation IDs, attempt ID, checkpoint ID, SHA-256, size,
and the existing save-offer filename. A receipt carries the same correlation
and checkpoint fields except the filename. IDs are exact positive integers
up to 2^53−1, save size is bounded to 512 MiB, and encoded messages to 4096
bytes. Unknown or duplicate fields, invalid formats, non-finite numbers,
unsupported versions, and malformed UTF-8/JSON are refused.
These bounds are stricter than the coordinator's general `_token` and integer
bounds: a `LoadOffer` accepted by the coordinator may be rejected here, for
example if its epoch contains spaces or an ID exceeds 2^53−1. An integration
must choose compatible values before creating offers; it must not silently
truncate, round or replace them.

`matches_offer(receipt, current_offer)` returns true only when every shared
field matches, including attempt, epoch, generation, hash and size. It does
not track which offer is current; the caller must supply the current one and
fence old connections, attempts and epochs. A matching message is untrusted:
it does **not** prove who sent it, that the client downloaded or loaded the
bytes, that X4 is paused, or that the game is compatible. It must never by
itself set `trusted_confirmation` or admit a player. Build/mod compatibility,
transport framing, authentication and native load confirmation remain the
responsibility of a future integration.

In particular, an old receipt still matches its old offer when both are passed
to `matches_offer`; the function neither stores state nor enforces increasing
generations, unique attempts, or an atomic freshness check. Attempt IDs must
be generated and not reused by the caller. `name` is an offer locator and is
not present in the receipt: two offers that differ only by filename both match
the same receipt. This does not prove where any bytes were received. A future
integration must decide whether to bind the locator and must enforce offer
ownership, freshness, authentication and native confirmation as one coherent
admission process.

The encoder emits one deterministic JSON representation, but the decoder also
accepts other valid JSON representations of the same message, such as changed
whitespace or field order. Equal decoded messages do not imply equal input
bytes. Do not sign or verify reconstructed bytes as if they were the original
wire bytes without separately defining an authenticated byte representation.

The codec and its Python tests do not demonstrate Windows behavior, Internet
connectivity, a shared universe, gameplay, or a production wire protocol.
