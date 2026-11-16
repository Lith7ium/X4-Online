# Private X11 one-key diagnostic: integration required

These default-off helpers are for a future isolated Linux flight diagnostic.
They do not launch X4, create a display, modify the normal profile, or claim
that X4 received an input. No real X11 or X4 input has been tested. They are
**not yet integrated into a native flight harness and must not be invoked on
the user's desktop**. The owner must supply and retain a newly created private
X server and private Xauthority file, one window, and the already owned X4
process. Display `:0`, remote displays and unverified ownership are refused.

`authority_x11_private_scope.verify` requires the supervising process's PID and
start ticks; a display process-group leader that is its direct child; an owned
Xwayland/Xvfb/Xephyr/Xorg PID, start ticks, executable and group; and both Unix
and abstract X11 listeners found for that display to be held by that server.
It requires a private mode-0700 directory and private regular, mode-0600-or-
stricter Xauthority file with a pinned digest. It also verifies the X4 launcher
is another direct owned process-group leader and the designated X4 PID/start,
executable and DISPLAY match that group and the private display. These are
sampled checks, not proof against adversarial PID/socket/file ABA changes.
The supervisor must independently pin the intended X4 executable and verify
that this private X server, Xauthority and display were actually created and
owned for this experiment; a user-supplied desktop display is not acceptable.

`OneKeyPulse(enabled=True)` may be used once by the main-thread supervisor,
only with a previously verified complete scope, a monotonic deadline no more
than 15 seconds away, and a live guard covering the owned X4, fixture, game
state, files and cancellation. An exec-gated, pidfd-owned child verifies the
scope again before opening X11. It requires `_NET_WM_PID` to equal the exact
owned X4 PID and the exact window to have X input focus. The sole permitted
pulse is keysym `a` for 0.05–0.5 seconds, interpreted by the private server's
keymap. The flight harness must separately validate the intended X4 binding;
this key may not represent strafe in a different layout or configuration. A
non-neutral key, unavailable property, lost scope/focus, changed process,
deadline or signal refuses or faults. Checks occur before and after potentially
slow calls, but focus and process checks are not atomic with XTEST dispatch.

The worker checks the server's key state after KeyDown and KeyUp. On ordinary
exceptions, SIGINT, SIGTERM and SIGHUP it attempts KeyUp in a `finally` path.
If GO was possibly dispatched and a confirmed UP receipt is missing, the
supervisor first terminates/reaps the original worker and starts a separately
exec-gated worker to release the exact keycode on the same verified private X
server. It checks server key state again. Worker/socket cleanup is required
before releasing the X4 lock; `KeyReleaseUnconfirmed` means the caller must
retain the lock and must not report success. A key already held before the
pulse is never intentionally pressed. Server key state is not a receipt that
X4 processed the input or release.

No software can promise KeyUp if the worker and its supervisor are both
killed or crash at the wrong moment, or if the X server/connection hangs or
disappears. In that case the independent release cannot be confirmed. The
owning lifecycle must fence the private X4 and X server, retain the ownership
lock while state is unknown, and explicitly stop/reap the owned disposable X4,
input helpers and private display before removing their resources. Destroying a
private display contains its input state; it is not evidence that X4 received a
KeyUp. Never attempt recovery against an unverified or ordinary desktop server.
The supervisor and its signal fences must remain alive throughout the pulse.

Tests under `test_authority_x11*.py` use fake X11 and actual private
exec-gated/pidfd helper processes. They exercise refused scopes, auth-file and
socket-ownership checks, signals/deadlines immediately before KeyDown, ordinary
KeyUp, worker death before/after DOWN, and failed emergency release. They do not
use X4 or an actual X server. Xvfb is not installed in the current environment;
no native SDL/XTEST, Xwayland, focus, keymap, window ownership or flight
behavior has been validated. Before a native run the integrated harness needs
an independent end-to-end review and tests of display ownership, signal fencing,
input/focus timing, observer handoff and cleanup with a private display.
