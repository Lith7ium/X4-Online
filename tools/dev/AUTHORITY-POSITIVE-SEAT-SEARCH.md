# Disposable positive-seat search probe

This opt-in local diagnostic is a test component, not an installed feature or
an automatic X4 runner. The caller owns one private X4 update loop, process,
protected files and paused load, and registers exactly the result, inconclusive
and refusal events for this probe. `new_x4` creates no callback or update loop.
The caller supplies a fresh 32-hex nonce, the saved registry epoch, the private
save path and a bounded deadline, starts once and never retries a request.

The read-only MD cue searches the current `player.zone` and requests at most 32
returned ships sorted by distance to the player's ship. The loop checks at most
those 32, excludes the player and non-operational/docked/stored ships, and
selects only a live ship with both an MD assigned pilot and a valid AI pilot
post reporting an occupied slot reservation. X4's `sortlimit` bounds returned
items and the loop, not its internal candidate search or sorting work. This is
not a census, and no candidate among the selected ships does not establish that
no positive control exists elsewhere. Missing/invalid slot or no candidate
produces a correlated inconclusive event; a getter expression error or missing
reply results in timeout/inconclusive, not an empty-seat observation.

The local Lua probe independently checks the returned ship, sector and zone
through FFI and requires a valid non-nil `GetComponentData(...,'assignedpilot')`
result. The original exact local actor IDs are not sent outside the local Lua/MD
callback or included in a result. Bad getter, ambiguous nil, invalid component
or context gives an inconclusive result; correlation, pause, time, unexpected
or late events fail closed. A timeout is an inconclusive observation, after
which late events still fault. Results and replies are one-shot; caller must
continue its own exclusive-owner, process, file, pause, event and deadline fences
through guarded use and cleanup. These checks are snapshots, not an atomic view.

A `candidate_observed` result says the MD reservation getter was nonempty and
that assigned-pilot getters returned non-nil/valid for the same ship under the
observed pause. It does not prove that the reservation and assignment identify
the same person, that a person physically occupies a chair, high attention,
coverage of nearby ships, or that a player's seat is free or controllable. It
does not authorize saving or integration with the disabled fixture save bridge.
The synthetic Lua and fake-FFI tests include an actor ID above 2^53 but do not
establish native ID, getter or event-serialization behavior. The bounded native
attempt below does not establish Windows, Internet or gameplay behavior.

## Private native harness

`authority_positive_seat_live.py` is a separate opt-in single-X4 supervisor using
the pinned two-sector checkpoint and the existing load/marker/slot-2/pause guard.
It installs only the search cue, its local module and owner in the private
protected overlay. The entire staged private save directory is mounted read-only;
the search has no ship-creation or save action. After the original load owner
has reached `done`, that same owner ticks the search; no second `onUpdate` is
installed. The private owner and probe use separate deadlines: the inner search
has at most ten seconds, and its timeout can be reported as inconclusive before
the outer deadline. The inherited sector-read guard also applies its original
30-second limit. No automatic request retries are made.

The final output distinguishes `outcome=candidate` from
`outcome=inconclusive`. In either case `success=true` means only that the
bounded diagnostic and final process/log/source checks completed; it does not
mean that an occupied physical seat was proven or that a seat is free. A fault,
late or duplicate callback, source change or unconfirmed cleanup makes the run
unsuccessful and suppresses the diagnostic outcome. Process and file checks
remain point-in-time observations, not atomic lifetime guarantees. The owner
uses no cross-process actor IDs, and its candidate reference is not retained for
subsequent operations. Neither outcome authorizes saving or gameplay claims.

## Recorded native attempt

The isolated Linux run `.local/authority-positive-seat-01` loaded the pinned
checkpoint, reported the expected marker, a paused slot-2 NPC read, and then
logged `START`, `INCONCLUSIVE`, `DONE` in order. Its result records
`success=true`, meaning the diagnostic and its final checks completed, with
`outcome=inconclusive`; it reports no owned processes remaining and no requested
checkpoint. The retained log does not identify the cause of the inconclusive
outcome. A missing or invalid context or slot, no qualifying result in the
bounded selection, an unavailable getter or a timeout are among the possible
paths; it does not establish that no candidate exists.

The archived source and private staged save both hash to
`2c6494308424fffe8bd114bd017802e2b6dc1f227a64998aea8a787672846748`.
The private search MD, Lua module and owner match their reviewed source bytes.
These file and process observations are point-in-time checks: they do not prove
byte-exact engine loading or continuous pause. This attempt proves neither a
usable seat nor player control, candidate coverage, same-person identity,
Windows/Internet operation or gameplay.
