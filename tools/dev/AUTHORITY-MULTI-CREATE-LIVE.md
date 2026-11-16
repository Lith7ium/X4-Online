# Private local Multi-Create experiment

This is a default-off diagnostic for a single isolated, paused Linux X4 process.
It uses the pinned 10,054-entry census checkpoint and the hash-pinned saved
sector witness inventory. The first eligible witness in each of two different
sectors is selected; X4 must still validate each current local witness. The
scenario issues two serial create operations and then replays each descriptor.
Every result is separately correlated and inspected through the local MD and
FFI paths. The save is privately staged with a read-only save directory; the
existing owned-process, protected-file, checkpoint marker, log continuity and
cleanup guards remain in effect. Pause is checked at the load owner and on each
scenario tick and FFI inspection; continuous pause between observations is not
proven.

The vessel macro `ship_gen_m_tugboat_01_a_macro` and faction `pioneers` were used
in the earlier bounded local replica experiment. The seed `7183`, placement
`(-400, 100000, 500)` in each local sector, and level-1 loadout are artificial.
The placement is not a collision-clearance guarantee. A witness may have moved,
become ineligible, or no longer resolve uniquely; failure is inconclusive and
must not be converted to success. No source process, TCP connection, real NPC
birth, complete ship state, Windows/WAN, gameplay, full universe coverage,
crash recovery, cross-process coordinate identity, or persistent multiplayer is
established. The temporary case is discarded on failure; never retry an
uncertain create within that case.

The script is invoked only deliberately by its CLI after independent review,
and only with a private, authenticated display and fresh output directory. It
must not be imported to start X4. The MD guard groups were shortened after a
previous unrelated X4 nesting-limit failure; schema validation does not prove
that a changed script will parse or run in X4.


## Bounded native observation, 2026-11-16

The single private Linux run `.local/authority-multi-create-01` reported
`success: true` and no remaining owned processes. The engine log records, in
order, the load request, checkpoint marker inspection and observed pause, then:

- create index `10055` in `cluster_01_sector001_macro`;
- create index `10056` in `cluster_01_sector002_macro`;
- replay index `10055` in the first sector;
- replay index `10056` in the second sector;
- scenario completion.

These are scenario receipts from one process. The scenario emits each row only
after the correlated MD Create/Inspect responses and its local FFI inspector
accept the object; the log does not independently expose the individual MD or
FFI observations or the local actor identities. The witnesses were selected
from the pinned saved census (indices 41 and 53 respectively) and checked by
the receiver during this run. The create requests used the synthetic seed,
placement and approximate loadout described above. This was not evidence of a
server-originated NPC birth or a source-to-client transfer.

The saved marker and sampled pause were observed; exact loaded-file identity
and uninterrupted pause were not proven. The result's owned-process list was
empty. These results do not establish TCP delivery, multiple clients, a Windows
client, WAN connectivity, synchronized simulation, full-universe coverage,
combat, trade, boarding, or persistence. No claim is made that the entire game
log is free of unrelated errors.
