# Isolated client checkpoint download and load observation

`tools/dev/authority_download_load_live.py` is an opt-in Linux-only diagnostic.
It starts no game on import. It requires a pre-existing current checkpoint from
one of the isolated, completed source-control runs accepted by
`authority_load_live.verify_origin`, a fresh private output under `.local`, the
pinned local X4 executable, and a private X11 display. It refuses to run while
another X4 process exists. Its source extension list must match the generated
client profile.

A deliberately synthetic server adapter publishes the existing checkpoint through
`WorldCoordinator`. The script offers this checkpoint using `SaveOffers`, receives
it over localhost TCP, verifies its size and hash, and puts it in a new disposable
profile. It starts one X4 process inside the existing bubblewrap namespace, with a
read-only staged save and protected configuration. The game is launched with the
existing isolated HOME, configuration, and extension allowlist. The launcher's
process and the X4 process identity are monitored; the protected files and Steam
identity are checked. The private result and engine logs remain under `.local`.

The actual client Lua load barrier emits an attempt-specific ticket on
`load_requested`, before `LoadGame`, and again on `pause_observed` after the
reinitialized UI sees a valid player and a paused game. The supervisor requires
both messages exactly once and in order, with every ticket field matching its
coordinator offer and fresh attempt. The session remains paused and the script
never calls `mark_loaded`.

Even when the diagnostic reports success, it does **not** establish which file
X4 actually consumed, that no simulation occurred before pausing, an actual
server-side save, real client admission, cross-platform content compatibility,
Internet connectivity, or shared gameplay. A hostile local process is outside
this controlled experiment's trust boundary. It is not a production client or
supervisor.

`tests/test_authority_download_load_live.py` exercises the TCP offer and download,
receipt rejection, and the real Lua barrier with simulated X4 calls. These tests
do not run X4. Native results must be recorded separately after an actual run.

On 2026-11-15, one isolated Linux X4 run completed this diagnostic. The
downloaded bytes matched the offered size and SHA-256, the ordered ticketed
load request and paused-player observation were received, and the owned
processes were stopped. The tested server adapter was synthetic; no client
was admitted. The exact file read by X4 remains unproven, as do all other
limitations stated above.
