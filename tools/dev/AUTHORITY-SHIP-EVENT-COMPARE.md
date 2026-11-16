# Local ship-event comparison observer

This is an opt-in diagnostic, not an installed extension or multiplayer path.
`authority_ship_event_compare.xml` listens for GoD-created ships, player-owned
ship completion, job-ship activation and objects entering `player.galaxy`. For
that last source it retains only objects X4 identifies as ships. It records the
source label, a local queue sequence, local actor reference and a snapshot of the
saved registry's bidirectional actor/index binding. Index `0` means no binding
was found, not that the ship is new. A faulty registry, inconsistent binding,
invalid ship, unavailable queued object, sequence limit or full bounded queue
faults the diagnostic. Missing events cannot be inferred from this queue.

Initialization is explicit; events before it succeeds are not captured. This
observer records candidates, not births. The event sources can overlap, an
object may enter a space without being created, and schema declarations do not
prove universe-wide subscription or completeness. Registry lookup is strictly
read-only: there is no `Enroll`, `Initialize` of the registry or ship creation.
The snapshot is local to the event; it does not prove a client counterpart or
cross-process identity. Unregistered actors are not added to the registry.

`authority_ship_event_compare.lua` is a separate serialized local UI owner.
One private, disposable X4 process must provide exclusive ownership of the MD
screen, event callbacks and update loop, plus an external process/profile guard,
monotone real clock, timeout and a local report sink. Its registry epoch is
pinned to the saved census; the separate queue generation is fresh and distinct.
Each Front and Ack has a fresh generation-scoped request ID and each complete
reply contains it in one atomic MD string; stale or duplicate results fault.
The expected hexadecimal actor format must pass exact native round-trip and
live ship checks; unparseable formats fault. A fresh, fenced X4 process with
no concurrent screen consumer is a mandatory caller precondition. UI callbacks
must not run synchronously within the dispatch call. Queue ACK follows only after the local
sink accepts the exact row and the guard is checked again. ACK here means local
observation consumed, never network delivery. On any uncertain outcome the
supervisor must fence the actual X4 process and keep its isolation lock until
owned cleanup; a Lua failed flag alone does not stop a running game.

The owner returns canonical decimal local actor keys to its local sink, never a
wire protocol. Its X4 binding parses hexadecimal actor text into exact `uint64_t` cdata,
round-trips the decimal value through the X4 ID conversion functions and
checks the resulting live object is a ship; rounded or unparseable values fault. `tests/authority_ship_event_compare.lua`
uses synthetic uint64 cdata values above 2^53 to check equal and adjacent unequal
IDs, along with timeout, bad order, missing actor and overflow notification.
`tests/test_authority_ship_event_compare.py` also checks the MD listener shape
and absence of registry writes. These tests do not establish the actual type,
value or lifetime returned by native X4; the binding fails closed when it cannot
validate a reference. The MD schema check validates XML structure only, not MD
runtime behavior or expression semantics. No event overlap is established.

## Prepared bounded native observation

`authority_ship_event_compare_live.py` prepares a separate opt-in, disposable
single-X4 diagnostic using the pinned census checkpoint and the existing
load/marker, protected-file, read-only save, owned-process and cleanup guards.
The load owner initially observes a pause; the observer initializes against
that saved registry, requests one resume and observes for a bounded wall-clock
window. It requests a final pause and drains pending observations until a new,
correlated Empty response is observed after pause. The Empty response is a
point observation, not proof that no event could occur later. Rows preserve the
local actor identity, source kind, sequence and registry index at capture.
No `Enroll`, ship creation, combat, trade or save is requested. The game is
nevertheless unpaused during the window and continues its normal simulation in
the isolated process; the staged save is not modified. Events after observer
initialization but before observed resume can also appear in the local log.

The result labels zero rows as inconclusive and never infers a ship birth,
complete universe coverage, network delivery or multiplayer. The MD event
actor's runtime formatting, local conversion/roundtrip, source-event reach,
callback timing and MD expression depth remain unproven by the offline tests.
The exclusive supervisor must discard an uncertain case and fence its actual
X4 process; no automatic retry follows a failure.

## First native attempt and a proposed scope correction

The one attempt `.local/authority-ship-event-compare-01` failed during the
second load pass, before marker, observer initialization, or any observation
row. X4 reported `Required attribute 'space' is missing` on the unfiltered
`event_god_created_ship` cue and then rejected its null event object. The local
XSD permits the attribute to be omitted, but that did not make the unfiltered
cue valid in this native load. The run reported no remaining owned processes;
independent post-run hashes matched the staged save to the source checkpoint
and the installed saved registry to the archive fixture. These post-run hashes
do not independently identify the bytes actually consumed by X4.

The revised cue supplies `space="player.galaxy"` as an experimental candidate.
An installed vanilla MD script uses that expression for a different event,
`event_object_entered`; this does not demonstrate that it is accepted for the
GoD event, is non-null at cue activation, or receives events across the entire
galaxy. Its runtime behavior and event coverage remain unproven. The static
test only enforces an explicit scope; schema validation is not a runtime test.
The later bounded observation is reported separately below.

## Second bounded native observation and offline ID comparison

The single follow-up `.local/authority-ship-event-compare-02` reported success.
After the load request, marker and observed initial pause, the X4 log records
`READY`, `RUNNING`, 21 sequential `activation` rows and `DONE 21`. The rows
contain 21 distinct local actor numbers, each with registry index 0; no `god`,
`player_build` or `galaxy_enter` rows were reported in this bounded observation.
This is not evidence that those event types never occur or that the observer
covers the whole universe. Registry index 0 is an absent binding at observation,
not a birth or proof the corresponding ship was absent from the saved world.

The runner's result reports a final observed pause and a correlated empty queue
sample. The log's `DONE` receipt is emitted by the reviewed owner only after
those conditions; the individual pause and empty response are not separately
logged as raw evidence. The event-list parser independently reproduced the 21
rows and source counts in `result.json`. Local X4 log game-time prefixes run
from approximately 3.04 at `RUNNING` to 63.05 at `DONE`; these are samples, not
proof of uninterrupted simulation or a complete event stream. A successful
load with the explicit GoD `player.galaxy` candidate did not establish that it
would deliver GoD events from any particular region.

A separate offline, read-only scan parsed the complete pinned save XML and
verified its compressed digest while reading. It compared the 21 *numeric*
local actor IDs, without any assumed conversion, to every component `id` under
`savegame/universe`. Fourteen numbers had no matching component ID; seven
matched component IDs whose saved classes were not ships: three `cargobay`,
three `dockingbay`, and one `turret`. For example, local actor number 89856
corresponds numerically to saved component `[0x15f00]`, a docking bay. The X4
observer had checked the runtime object as a ship. These are raw number matches
only: a runtime-to-save ID translation or runtime ID reuse is not established.
The data cannot determine whether any of the observed ships existed before the
run and must not be used as a birth classification or 1:1 identity mapping.

After the run, the staged save and the source checkpoint both had SHA-256
`64a233ac6a85194b8276212709e78a6c48bbcc0f73c19842622aa098f1408cb8`;
the installed saved-registry script and archived fixture both had SHA-256
`8b7c9887c9c1476e45fe84a60243547d96e09b11d4c40fabd151930af517e939`.
The installed observer MD had SHA-256
`e233abd9490981be9b4b7563ea7f7c5f06d0ccaa1bc01e29361cd598d69e9bd5`
and matched the reviewed source, as did the installed Lua modules after their
specified installer transformation. These post-run comparisons do not prove
which exact file bytes X4 consumed. The result recorded
`owned_processes_remaining: []`; a separate post-run X4 executable inventory
was empty. Neither run establishes source-to-client transfer, multiple X4
participants, Windows/Internet, gameplay or persistence.
