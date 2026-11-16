# Private display feasibility (investigation only)

Do not use the existing input helper on the strength of the observations
below. A bounded Xvfb display probe was run without X4, windows or input;
it is not an integrated display or flight-test supervisor.

## Bounded Fedora Xvfb probe

Fedora 45 `xorg-x11-server-Xvfb` and `xorg-x11-server-common`, both
`21.1.26-1.fc45.x86_64`, were downloaded from the configured Fedora
repositories and verified with the installed Fedora 45 signing key before
private extraction. `rpmkeys --checksig --verbose` reported valid OpenPGP
signatures and header and payload SHA256 digests. RPM SHA256 values were:

* Xvfb: `8622edecc6ff0084e4f13e631db07cedb9ba902375e2f64f969e7244417a5a34`
* Common: `1706e06e9594c1f0b3550e64963a85eb9ace5f3279eab482a8373301fba9b7a7`

Both were extracted under `.local/xvfb-fedora-45.AoId7Mk9/root`; this did
not install packages or map their absolute filesystem paths. All dynamic
libraries in the extracted Xvfb binary resolved with `ldd`; Xvfb's declared
common package is not installed in the system RPM database. The native probe
and its result are `.local/xvfb-probe-01/probe.py` and `result.json`.

The probe started that Xvfb in its own process group with a randomly selected
display number, a private mode-0700 directory, fresh separate mode-0600
correct and incorrect cookie files, and `-nolisten tcp`. `xdpyinfo` connected
with the correct cookie. With a wrong cookie, and separately without
`XAUTHORITY` under a private `HOME` without a default `.Xauthority`, the
probe classified both failures as explicit authentication rejection. Probe
stderr was classified in memory and was not saved separately, so those raw
messages cannot be independently inspected afterward.

Before and after probes, the matching Unix-path and abstract X11 socket inodes
were found among file descriptors of the expected Xvfb process. This is a
sampled ownership check: the parser did not check the listener flag or handle
multiple entries for the same socket path. TCP absence was not separately
verified. The owned server exited and was reaped; no process-group members or
matching socket paths remained. The server log records XKB warnings and an
AMDGPU initialization warning. This probe demonstrates neither X4 or Vulkan
operation nor window PID, focus, keymap, input delivery or safe integration of
the input helper. Signal handling covered normal termination signals, not an
unrecoverable supervisor kill or machine failure.

The installed `Xwayland -help` lists `-auth file` and `-displayfd fd`.
The installed `kwin_wayland --help` lists `--virtual`, `--xwayland`, and
`--xwayland-xauthority`. These are command-line capabilities, not proof that
the resulting server enforces a private cookie or that its processes fit the
ownership contract of `authority_x11_private_scope.py`.

An older private KWin/Xwayland experiment is documented under
`preparation/native-linux-controls-20261110/virtual-display-20261113/` in the
project directory. Its `start.py` creates an empty authority file, while
`session.py` and `verify.py` explicitly describe local-user ACL access and
the authority file as a compatibility placeholder. Its successful window
observation therefore does not establish cookie authentication. It also uses
`dbus-run-session` as the process-group leader; the complete current
input-helper scope and cleanup contract have not been demonstrated by it.

A possible next investigation is a private virtual KWin Wayland compositor
with a separately owned rootful Xwayland using a private `-auth` file and
`-displayfd`. This is a hypothesis, not a validated command or a launch
approval. It still needs a private Wayland-socket binding, a process-group and
exec-gate design compatible with the existing supervisor, explicit listener
ownership and executable checks, and confirmed cleanup of all owned children.
Alternatively, KWin's `--xwayland-xauthority` might provide a route, but its
actual treatment of credentials and inherited process identities is not
established by the help text.

Before treating any candidate as usable, a bounded read-only display probe
must verify the owned server and listeners before connecting and recheck their
identities at probe boundaries and through cleanup. It must check that the correct private credential
connects and that both a wrong credential and no credential are explicitly
rejected while the same owned server is live, excluding inherited credentials
and automatic credential discovery in the negative probes. A timeout, crash, missing
library, or lost server is inconclusive, not an authentication rejection.
Only after this may a separately owned harmless window be used to examine its
PID property and focus. All probes must be reaped, cleanup failures remain
unconfirmed, and no normal desktop access, X4, keyboard, or mouse input is
allowed. The checks are sampled and do not establish adversarial atomicity.

Until a concrete adapter meets those conditions and the ownership gaps above
are closed, input-helper readiness remains unproven; it must fail closed.
