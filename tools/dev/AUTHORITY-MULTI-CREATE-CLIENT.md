# Experimental correlated multi-create client

The default-off `authority_multi_create_client.lua` and
`authority_multi_create_receiver.xml` are a serial isolated experiment. Neither
installs an update handler, opens a socket or provides an X4 FFI adapter. The
existing receiver and legacy diagnostics are unchanged. The receiver uses a
separate MD script/screen and is derived from the two-sector fixture receiver.
Its experimental dynamic lookup accepts a per-request index into the local
save-baseline registry, not a reference from another process. It requires that
the indexed witness be operational, undocked, reverse-mapped and in the one
local sector matching the requested macro. The MD Inspect repeats this check.
There is no real X4 result for this new combined receiver.

The exclusive caller must verify the common save/registry epoch, baseline
index, compatible saved registry and witness provenance, supported macros,
trusted actor ownership and isolated execution before initializing, provide a
fresh nonce, and route the single
qualified `X4AuthorityMultiCreateReceiver.Result` event. `issue` must confirm
an asynchronous dispatch; nil, exceptions, overlapping requests or unexpected
responses fault the client. It consumes a new request ID for each Initialize,
Create and MD Inspect. A missing or indeterminate response is never retried.

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
FFI/property checks. No real inspector is supplied here. An actor collision,
changed actor on replay, failed guard, clock or callback, invalid response or
timeout faults the instance. The completion callback is provisional until
`event` returns true; it must not irreversibly act during that callback.

The MD receipt tables and in-memory Lua records are not a crash-durable
transaction. Existing saved indices are not adopted, no destroy or autonomous
NPC deduplication is implemented, and pause/clearance/parent checks belong to
the real owner. The descriptor's seed is caller-provided; this code does not
infer or fabricate the source ship's seed. The receiver's loadout is an
approximation and omits ship state. A lost dispatch or interrupted mutation
requires fencing and discarding the isolated test case. No Lua/Python bridge,
native correlated-event or FFI-inspector result, gameplay, WAN or Windows
operation has been established by these synthetic tests.

Focused tests: `python3 -m unittest discover -s tests -p
'test_authority_multi_create_client.py' -v`.
The MD document also passed the installed X4 `08.cat` MD schema; the temporary
XSD extraction was checked against the catalog digests. Schema validity does
not establish expression behavior in the game. The inherited Create guards
and new witness checks contain long expressions; X4 previously rejected an
unrelated guard at runtime with `Maximum operator nesting level reached`.
Before any native attempt, review and, where needed, split these expressions;
the present synthetic and schema checks do not rule out the same parser limit.
