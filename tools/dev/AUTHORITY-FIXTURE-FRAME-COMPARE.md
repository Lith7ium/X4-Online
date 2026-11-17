# Fixture station-frame comparator

`authority_fixture_frame_compare.py` contains the 12 and 8 station candidates
inventoried in the confirmed `checkpoint-cac780ceccbd405ea367dfe028a5ae9d`
(SHA-256 `51191bbc99cca5ebcf319acccde4d48198b30a391bbb0a449fcacde15bda0746`).
Each saved code occurred once in that checkpoint. Their presence in a save does
not establish that X4 can find them, that they are operational, or that their
serialized offsets are sector coordinates.

The comparator accepts two supplied collections of station rows, indexed by
fixture slot. A row contains `code`, `macro`, `owner`, `sector` and a three-part
`position` already measured in that process's sector frame. It checks each
row against the saved candidate identity, then requires at least three common
noncollinear anchors per sector in both inputs and at most one coordinate unit
between corresponding positions. It reuses the thresholds and geometry check
from `authority_saved_frame_compare.py`.

The caller must verify the exact source checkpoint and selected saved scripts,
perform and correlate the native reads, check local actor/sector references,
pause and process ownership, and fence failures. This standalone function does
none of those things, makes no X4 or network calls, and returns no native
handles. Synthetic unit tests and a matching result cannot establish runtime
measurement, cross-process identity, a universal frame, continuous pause or
multiplayer gameplay. Sectors, anchors and ownership in later saves may change;
a changed inventory requires a separately verified fixture, not relaxed checks.
