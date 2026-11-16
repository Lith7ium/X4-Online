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
monotone real clock, timeout and a local report sink. Its epoch and generation
are fresh and distinct. Each Front and Ack has a fresh generation-scoped request ID and each complete
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
runtime behavior or expression semantics. No X4 run or event overlap is asserted.
