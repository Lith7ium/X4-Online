# Isolated string-based registry resolve experiment

This default-off diagnostic is separate from the failed table-valued ResolveV2
attempt and leaves the original registry and its events unchanged. It is not a
production protocol. The local X4 9.00 `common.xsd` documents a string as an
allowed `raise_lua_event` parameter; it does not establish what `%s` produces
when formatting a component reference.

The MD cue checks epoch, registry state, index, ship validity/class and the
reverse mapping, then emits one string containing request ID, epoch, index,
status and the actual resolved component formatted with `%s`. This is the
component itself, not its player-facing `idcode`. One native diagnostic
observed a parseable local hexadecimal ID for one ship, as described below.
Additional text, wrong
fields, missing responses, mismatched IDs and malformed or nonhex values fail
closed. An unavailable response carries the sentinel `0`; it does not establish
that the object was destroyed.

LuaJIT FFI parses one to sixteen hexadecimal digits with the required `0x` or
`0X` prefix, by multiplying and adding `uint64_t` values one nibble at a time. It does
not convert the 64-bit value through a Lua floating-point number. Zero and more
than sixteen digits are rejected. The resulting value must match the exact
`uint64_t` actor ID retained directly from the fleet FFI result before conversion
to a Lua actor, and that actor must still be valid. A `ConvertIDTo64Bit` result
may be a Lua number only if it is a finite integer from 1 through 2^53−1; it
must round-trip to that retained FFI ID. Lua numbers at or above 2^53 are
refused. A genuine `uint64_t` can represent larger values and is compared
directly to the retained ID.
The test set includes the maximum unsigned 64-bit value and values above 2^53;
those large values were tested synthetically only.
The actor ID is strictly local to this X4 process and is not a portable identity.

An explicit `false` from `AddUITriggeredEvent` faults the probe. A `nil` return
does not confirm dispatch; only a matching response can complete the request,
and the deadline remains in force.

The separate `authority_registry_resolve_string_live.py` reuses the isolated
single-X4 lifecycle and cleanup of `authority_registry_resolve_v2_live.py`,
but installs only the string cue and probe into the private overlay. It selects
one already existing operational ship, checks its result and then an unavailable
index while paused. It requests no save, creates no test ship and uses no
position setter. The private log records response types and actor-format shape,
not actor values. Sampled pause checks do not prove uninterrupted pause.

One isolated native attempt, `.local/authority-resolve-string-01`, returned a
string to the first callback but failed the actor response check and confirmed
owned-process cleanup. Its log reports a hexadecimal-looking final field of
length seven, but the old shape logger did not distinguish a required `0x`
prefix from unprefixed digits and discarded the client's specific rejection
reason. The field, envelope and actor value were not recorded, so the precise
cause cannot be recovered from that log. The unavailable request was never
reached; this run did not validate the actor comparison.

The instrumented `.local/authority-resolve-string-02` run reported a string
with `0x` prefix and matching request, epoch, index and status, then rejected it
as `actor_mismatch` with `expected_type=number`. The former adapter refused all
Lua numbers before performing the actual ID comparison. The original failed
result is preserved; this observation does not prove whether the MD-formatted
ID equals the local actor. The revised probe described above retains the fleet
FFI ID as the comparison reference. Synthetic checks cover a safe small numeric
round-trip, rejection of Lua numbers at 2^53, and an exact uint64 ID above 2^53.

The subsequent isolated `.local/authority-resolve-string-03` run reported
`success=true`, confirmed native pause and owned-process cleanup. For one
already known local ship, its log reports matching request ID, epoch, index
and status and `ACTOR_MATCH` after comparing the parsed MD string against
the retained fleet FFI ID. A second request for an unavailable index returned
the expected correlated `UNAVAILABLE` result. The log's actor field had seven
characters including `0x`; large uint64 IDs remain synthetically tested only.
The earlier failed results were not changed.

The private diagnostic reports only the prefix class, shape and length,
Boolean request/epoch/index/status matches, an enumerated rejection reason and
the type of the independent actor reference. It does not log request IDs,
epochs or actor values.

This local test did not establish resolution of an unknown actor ID, save/load
identity, cross-process or Windows/Internet behavior, sessions, combat, trading
or multiplayer. The caller
must serialize requests, avoid ID reuse across adapters and fence old callbacks;
timeouts poison the experiment.
