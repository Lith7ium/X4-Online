# Isolated trusted-marker admission experiment

`tools/dev/authority_trusted_marked_live.py` is an opt-in Linux-only diagnostic.
It starts two exclusively owned X4 processes with disposable profiles under a
private output directory. The server creates and marks a checkpoint; the client
downloads it over localhost, loads it, and reports the saved marker after X4's
load event and a paused player. Under the cooperative-client assumption, the
experiment accepts that attempt, requests native resume on both processes,
then requests pause when a second simulated connection arrives. It stops with
the newly required save pending; it does not complete that second join.

The experiment checks staged size and hash, two selected saved fixture names
and macros, the marker and ordered load receipts, and owned process identities.
It checks the control context immediately before admission and limits later
native control calls to the remaining deadline. These are point-in-time checks,
not a continuous pause guarantee or proof of the precise bytes X4 consumed.
The caller trusts the observations produced by the controlled client. Server
extension files are not independently fenced against another process changing
them. Process cleanup checks the owned process groups; it is not proof that an
arbitrary descendant could not escape those groups.

This is not an Internet or Windows test and does not exercise a human player,
ship replication, trade, combat, boarding, persistent-world restart, or a
playable multiplayer session. Running it requires a pinned Linux X4 install,
Bubblewrap, and an isolated virtual X11 display. Normal saves are not selected
by this test harness. Results and private logs are written only under its fresh
`.local` output directory.

```sh
python tools/dev/authority_trusted_marked_live.py --game /path/to/X4 \
  --out .local/trusted-marked-experiment --display :2 --timeout 600
```
