# Two isolated Linux X4 checkpoint experiment

`tools/dev/authority_two_x4_live.py` is a disposable diagnostic, not a
multiplayer launcher. It starts two isolated Linux X4 processes under one
supervisor and requires the pinned local game build, a running Steam session,
Bubblewrap, and a separately provisioned local X11 display. The output must be a
fresh path under the repository's `.local` directory.

The first process autostarts an isolated creative world and enrolls its native
control bridge. `WorldCoordinator` requests pause and save, publishes the
verified checkpoint, and offers it through `SaveOffers`. The supervisor
transfers the bytes over local TCP to a new client profile and starts the second
process with that save and its probe configuration mounted read-only. It checks
for the probe's load-request and paused-player observations while both owned X4
processes remain alive. The server coordinator remains paused; the client is
never admitted and there is no gameplay or Internet test.

The optional `/proc` observation samples the running client for open regular
file descriptors matching the staged save's device and inode, validates a
reopened descriptor with `fstat`, and records the largest sampled `fdinfo`
offset. Absence of a sampled descriptor does not establish that the file was
never opened. A matching descriptor or offset does not prove a complete read,
loading, or world identity. The probe receipts likewise do not prove which
bytes X4 used. Do not treat this experiment as a real client join.

Each process has its own disposable home, save folder, game view, and lock file.
The supervisor refuses an existing host lock target and releases only the inode
it created. It terminates only its own launch process groups. Running the script
is optional; importing it starts nothing. Example with an already prepared
virtual display and Xauthority:

```
python tools/dev/authority_two_x4_live.py --game /path/to/X4 \
  --out .local/two-x4-experiment --display :2 --timeout 600
```

On 2026-11-15, one native Linux/Linux run completed this sequence. The server
bridge confirmed pause and produced a verified checkpoint, whose bytes were
transferred to the second profile. The client emitted the ordered load request
and paused-player observation while both processes remained alive. The
coordinator remained in its paused state, although the test did not monitor
the server's native pause flag continuously. During the client run a matching
open descriptor was sampled, with a maximum reported offset equal to the
25,464,699-byte staged file size; sampling includes save-list inspection, and
an offset may be produced by seeking. This is not proof of a complete read or
of world identity. Both owned process groups were stopped after the run. No
client was admitted and gameplay was not tested.

Automated tests cover transfer from a coordinator-backed checkpoint, no
admission, and sampled file-descriptor identity/offset. Those tests use doubles.
