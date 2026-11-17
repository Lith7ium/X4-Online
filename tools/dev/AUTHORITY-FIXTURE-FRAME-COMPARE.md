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

On 2026-11-17, two sequential isolated Linux X4 processes loaded the confirmed
fixture checkpoint and used the read-only MD/FFI probe to measure station
positions while paused. All 12 candidate stations in the first sector and all
8 in the second were found in both runs. The maximum measured position delta
was zero in each sector, and both anchor sets passed the noncollinearity check.
The private outer scope confirmed process and display cleanup and unchanged
Steam identity. The complete local results are in
`.local/private-fixture-frame-scope-real-20261117-01/`.

This result supports these station frames for these two Linux reloads of that
checkpoint only. It does not prove that X4 consumed the exact staged bytes,
that two runtime ship references identify the same actor, that other frames or
Windows match, or that positions are applied or replicated during gameplay.
