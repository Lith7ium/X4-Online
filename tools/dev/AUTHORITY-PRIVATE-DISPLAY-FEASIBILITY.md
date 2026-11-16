# Private display feasibility (investigation only)

There is no runnable private-display experiment in this change. Do not use the
existing input helper on the strength of the observations below. No display,
X4 process, or input was started for this investigation.

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

Until a concrete adapter meets those conditions, native readiness and private
authentication remain unproven; the experiment must fail closed.
