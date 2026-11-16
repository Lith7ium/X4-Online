# Experimental correlated multi-create client

The default-off `authority_multi_create_client.lua` and
`authority_multi_create_receiver.xml` are a serial isolated experiment. Neither
installs an update handler, opens a socket or provides an X4 FFI adapter. The
existing receiver and legacy diagnostics are unchanged. The receiver uses a
separate MD script/screen and is derived from the two-sector fixture receiver.
Its experimental dynamic lookup accepts a per-request index into the local
save-baseline registry, not a reference from another process. It requires that
the indexed witness be operational, undocked, reverse-mapped and in the one
local sector matching the requested macro. The MD Inspect repeats this check. A bounded native observation of this
receiver in one isolated Linux X4 process is described below.

The exclusive caller must verify the common save/registry epoch, baseline
index, compatible saved registry and witness provenance, supported macros,
trusted actor ownership and isolated execution before initializing, provide a
fresh nonce, and route the single
qualified `X4AuthorityMultiCreateReceiver.Result` event. The `issue` callback
must return exactly true to indicate the asynchronous dispatch was attempted;
that alone does not prove delivery. A matching response remains required. A nil
callback result, exception, overlapping request or unexpected response faults
the client. It consumes a new request ID for each Initialize,
Create and MD Inspect. A missing or indeterminate response is never retried.
A correlated MD refusal includes a fixed phase code for the first checked
failed group (for example `create_witness`, `create_ship`, `inspect_binding`
or `inspect_witness`); multiple conditions within that group can fail. The
client accepts only codes appropriate to the pending operation and still
accepts legacy empty refusals. These codes describe the executed branch, not
the exact cause or a guarantee that no mutation preceded the refusal.

For each Create, a new index must be exactly the next one. An index previously
created by this client instance can be replayed only with the exact original
descriptor; a different eligible witness for the same sector may be supplied
on a replay. Witness indices must refer to the saved baseline, not dynamically
created actors. Some sectors have no eligible saved witness, or a witness may
move or become unavailable; those cases fail and need separate handling. Local
uniqueness and matching sector macros do not prove a cross-process frame. After
`Created`, a separately correlated MD `Inspect` verifies the
local forward/reverse registry, receiver-owned binding, stored descriptor and
current macro/sector/owner. It returns actor and sector as hexadecimal local
references. The client parses the actor exactly without Lua number rounding and
requires the injected `inspect(actor_hex, sector_hex, index, descriptor)` to
return `(canonical_decimal_actor_key, true)` only after independent local
FFI/property checks. The separate opt-in
[X4 inspector](../../src/authority/MULTI_CREATE_FFI_INSPECTOR.md) provides
those checks for a paused isolated profile. An actor collision,
changed actor on replay, failed guard, clock or callback, invalid response or
timeout faults the instance. The completion callback is provisional until
`event` returns true; it must not irreversibly act during that callback.

The MD receipt tables and in-memory Lua records are not a crash-durable
transaction. Existing saved indices are not adopted, no destroy or autonomous
NPC deduplication is implemented, and pause/clearance/parent checks belong to
the real owner. The descriptor's seed is caller-provided; this code does not
infer or fabricate the source ship's seed. The receiver's loadout is an
approximation and omits ship state. A lost dispatch or interrupted mutation
requires fencing and discarding the isolated test case. The synthetic tests
do not establish a live Lua/Python bridge, gameplay, WAN or Windows operation.

Focused tests: `python3 -m unittest discover -s tests -p
'test_authority_multi_create_client.py' -v`.
The MD document also passed the installed X4 `08.cat` MD schema; the temporary
XSD extraction was checked against the catalog digests. Schema validity does
not establish expression behavior in the game. The long Create and witness
guards were split into short, nested conditions that retain their original
evaluation order. X4 previously rejected an unrelated guard at runtime with
`Maximum operator nesting level reached`; schema and offline tests alone do
not establish parser or runtime behavior.


The bounded native Linux run `.local/authority-multi-create-01` logged two
serial creates and their replays in two census-witnessed sectors, followed by
scenario completion. Its code emits those rows only after the correlated MD
responses and the local FFI inspector accept each operation; the individual
MD and FFI observations are not logged independently. The run used artificial
seed, coordinates and loadout in one isolated process. It did not test source
events, TCP delivery, multiple clients, gameplay, Windows or Internet operation.
See [the native observation](AUTHORITY-MULTI-CREATE-LIVE.md) for its limits.
