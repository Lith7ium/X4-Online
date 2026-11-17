# Experimental registration of the saved player fixtures

This opt-in owner appends two already saved Company fixtures to the historical
`X4AuthorityShipRegistry`. It does not start X4, save, assign seats, transport
data or install an update loop. The historical registry and previously saved MD
scripts remain unchanged. A separate owner must load a disposable copy of the
confirmed fixture checkpoint, prove its marker and paused state, and fence the
process, profile and all event traffic for the entire experiment.

The recorded confirmed fixture checkpoint
`checkpoint-a3cf97a14b394b408d34513e3658c9ab`, SHA-256
`86795a48053de8f05a4467ba1286479eef116a1e4ba170f227ea98d8b6f72556`,
passed `authority_registry_save_evidence.verify` with the archived fixture
epoch, count 2 and complete forward/reverse agreement. This is evidence about
the saved bytes, not independent proof of which file X4 loaded or which runtime
actor each reference denotes. The owner is intentionally restricted to that
two-entry starting shape and expects the two new indices to be 3 and 4.

`authority_player_registry_read.xml` is a new, read-only MD cue that reports a
fixture's process-local actor and sector after checking its saved fixture state,
owner and context. `authority_player_registry_enroll.lua` uses the existing
`ship_registry_client.lua` in its **uncorrelated legacy mode**. After checking
the epoch and count, it reads each fixture in slot order and performs Enroll,
Resolve and a repeated Enroll. It then checks the final count. The result from
`take_result()` contains only `{indices={3,4}, count=4}`; actor and sector
handles stay within the process. These checks are sampled, not atomic. A
detectably unexpected, late, duplicate or missing response, a failed guard or
uncertain dispatch faults the owner; discard the disposable world and do not
retry the operation there.

The existing recovery onUpdate owner must construct `new_x4` with the fixture
epoch, a fresh nonce, timeout, exact private save path, the existing resolver
and registry modules and an external process guard. It
must register and exclusively route `X4AuthorityPlayerRegistryRead.Result` to
`fixture_event`, route its `Refused` to `refused`, and route the historical
`X4AuthorityShipRegistry` event suffixes to `registry_event`. It must call
`start` once and `tick` while pending, call `take_result` only after `tick`
returns true and the state is `done`, watch for late responses until process
stop, and never run a competing user of these uncorrelated registry events.
An uncorrelated response is not independently tied to a specific request:
a delayed identical `Enrolled` receipt can be indistinguishable from the
current response. Absence of such stale or duplicate traffic, exclusive
ownership and fencing of prior process incarnations are assumptions.
Module construction and event registration do not supply those fences.

`authority_saved_player_registry_live.py` connects this owner to the existing
private saved-seat reload runner. Its installer modifies only the private UI
copies: the recovery update invokes the registry owner first and the seat owner
only after the ordered registry receipt. Its log watcher requires that receipt
between the confirmed pause and the seat start. It writes a separate
`registry-result.json` and preserves the underlying recovery result. This path
is offline-tested only; it does not request a save and cannot establish the
saved registry mapping. The same uncorrelated-event and exclusive-process
assumptions apply.

After successful runtime enrollment, an owning experiment must save and verify
the marker and checkpoint bytes, then call
`authority_player_sector_evidence.verify(..., registry_count=4,
fixture_indices=(3, 4))` before confirming that saved checkpoint. A saved
registry comparison does not prove client binding, seat control, motion,
Windows or multiplayer. The current offline tests use a synthetic registry and
synthetic LuaJIT FFI; neither the MD expressions nor the integration have run
in X4.

## First combined native attempt

In `.local/private-registry-scope-real-20261117-01/`, an isolated Linux X4
reload logged the fixture marker, pause and `ENROLLED 3 4` registry receipt,
then started the saved-seat sequence. The supervisor stopped with `local
evidence file changed while reading` before seat completion and reports failure;
the exact filesystem change that triggered it was not recorded. The private
scope reports cleanup and unchanged Steam identity. The log receipt is a
bounded runtime observation, not a completed end-to-end result or proof that
the new mapping was saved. No save was requested in this run.

A subsequent isolated run, `.local/private-registry-scope-real-20261117-02/`,
used a single checked log snapshot per polling cycle. X4 recorded the marked
load and pause, `ENROLLED 3 4`, then the complete guarded control sequence for
saved slot 1. The runner reports success and an empty owned-process list; the
outer private scope reports display and process cleanup and unchanged Steam
identity. The individual legacy replies are validated by the owner but not
independently retained in a packet trace. The registration was in memory only:
no checkpoint with the four-entry mapping was saved or reloaded. This does not
establish cross-client identity, player flight or multiplayer.

## First registered checkpoint attempt

`.local/private-registry-save-scope-real-20261117-01/` loaded the same source,
registered both fixtures, observed slot 1 control and requested one native
save. The experiment reports that the published save passed the complete
four-entry registry and fixture-reference check and native verification. It
was **not confirmed**: the final recovery receipt check failed after a marker
load probe logged `AUTH_MARKER load ERROR` when the save bridge emitted a
legitimate later `Stored` event. The load probe's handler also listened for
that event after its load phase; this is an identified event-handler conflict.
The outer scope reports process/display cleanup and unchanged Steam identity.
The unconfirmed checkpoint remains diagnostic evidence and must not be used as
a confirmed recovery point.

A subsequent isolated run, `.local/private-registry-save-scope-real-20261117-02/`,
used the corrected load-marker event handling and reports a confirmed checkpoint
`checkpoint-a8f08704fd1d42cd9c73f17256c27f73`, SHA-256
`e06b7475db27aa614150798cf2dac50ab91d8fec24cb7b59d582a3c006e67112`.
The experiment reports native save and VERIFY, a saved fixture-to-registry
check for indices 3 and 4, and confirmation after owned-process cleanup; the
outer scope independently retrieved the confirmed checkpoint and matched its
identity and hash. Private display and process cleanup and unchanged Steam
identity were reported. This is one confirmed saved mapping, not a proof of
exact loaded bytes, later reload, stable identity across game processes, player
flight, Windows or multiplayer.

## Reload of the confirmed mapping

`.local/private-registry-reload-scope-real-20261117-01/` loaded a private copy
of the confirmed four-entry checkpoint in a fresh Linux X4 process. After the
expected marker and pause, X4 logged `MATCHED 4 3 4` from the separate
read-only MD comparison of both saved fixture references, their sectors and
forward/reverse registry positions. The runner reports success and no owned
processes remaining; the private scope reports cleanup and unchanged Steam
identity. The new cue also passed the stock MD schema. The legacy Resolve cue
was not invoked, and no enrollment or player-seat change was requested. This
is bounded evidence for two saved fixtures in one reloaded process, not proof
of exact file consumption, identity across clients or multiplayer gameplay.

The repository-wide development check after these changes ran 4,743 tests with
no test failures and 26 skips. Under the repository policy, skips make the
check incomplete. Remaining skips require Windows or unavailable reference
inputs; the detailed local log is
`.local/check-authority-registered-motion-windows-reload-20261117.log`.
