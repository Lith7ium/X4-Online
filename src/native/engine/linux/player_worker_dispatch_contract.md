# Worker dispatch contract (engine-free)

This default-off contract supplements `frame_worker_recurring.h`. It cannot
prove a native frame owns a particular semaphore wake, and it does not enable any
hook. Use in a native session remains blocked until the bootstrap and all relevant
semaphore users are authenticated.

The opt-in adapter must compose with the existing `lmt_worker_wait` at the pinned
movement wait, and with the admitted main FrameTick post sites. It must retain
original arguments, invoke each original exactly once, and preserve the full raw
return and incoming/outgoing `errno`. The post-begin mark precedes the original
post, because a waiting worker can wake before that call returns. The existing
post-join boundary must wait, with a deadline, for post-return and the matching
movement wait before allowing `fwrr_worker_arrive`; the existing FWRR token and
tail release then own the rest of the generation. Any contract failure must stop
before native simulation resumes. The adapter must authenticate the semaphore,
threads, pinned sites, and the native return semantics independently.

Bootstrap must rule out a queued permit and an already awakened old pass, not
merely observe a zero count. The other known wait site and all post paths must be
accounted for during the active scope; an unexpected consumer, post, or shutdown
fails closed. The static reference audit does not exclude dynamically computed
aliases. No test in this fixture proves those native facts, general writer
exclusion, disconnect handling, or a persistent session.

The resident implementation is in `player_worker_dispatch_adapter.h` and
`gate_player_worker_dispatch.h`. The finite runner enables it explicitly with
`--worker-dispatch --semaphore-observer`; it sets `X4_DEV_WORKER_DISPATCH=1`
only from the frozen manifest. The callback remains active after observation
closure. Bootstrap requests at take-1, synchronizes that native startup post,
forwards any pending old wait unchanged, then parks at an empty next prewait.
Every admitted dispatch carries its own worker TLS ticket; its next prewait,
after native tail work, retires the generation. No permit is drained or rewritten.

Synthetic threaded tests and successful compilation do not establish native
progress or complete access coverage. Keep the finite discard boundary until
bounded native testing establishes those facts for the pinned image.

Session stop is terminate-only once takeover registration is requested. The
independent stop latch in `gate_player_dispatch_stop.h` arbitrates registration
against `finish` before any legacy cleanup; it survives `stats.active` changes.
Requested/published takeover exits 225 with a terminal reason, preserving resident
callbacks until process death. A legacy stop keeps its prior cleanup behavior,
but later takeover in that process is refused. Neither hook restoration nor
callback unregistration is supported for resident dispatch. Finite completion
still uses exit 223 and retains its existing budgets and deadlines.

Local launcher stop is a separate, opt-in capability: set
`X4_DEV_PLAYER_STOP_FD` to the canonical decimal descriptor (at least 3) of an
inherited read-only, nonblocking anonymous pipe, together with
`X4_DEV_WORKER_DISPATCH=1`. The gate pins this configuration once and owns a
private CLOEXEC duplicate; it never reads or closes the inherited original.
It checks the duplicate's identity and flags before reading. Send one ASCII
`S` byte to request stop. EOF, malformed bytes, invalid configuration, and
channel faults also terminate the isolated process with exit 225. Reasons are
226 (invalid), 227 (request), 228 (EOF), and 229 (fault), and 230 (foreign/concurrent/reentrant polling). Before takeover this
uses the terminal path directly; after takeover it uses `finish` and the existing
terminate-only latch. Neither path restores hooks or resumes singleplayer.

The main gate polls at entry and before native forwarding, and on both sides of
its 25 ms permit receive. Shared window-check polling also covers handshake and
lookahead waits. Polling preserves `errno` on the no-stop path. No environment
setting leaves the default behavior intact. Human window close is unsupported
in this development mode; a native call that blocks without returning still
requires the launcher's bounded, owned-process fallback. This capability stops
only its local isolated game; it does not grant privileges over an external relay.

Only the actual `gate_tick` entry may initialize an opted-in channel and publish
its OS-thread owner. Atomic configuration states prevent shared wait callers
from accessing a partial descriptor or identity. A READY-to-POLLING transition
excludes concurrent/reentrant reads; foreign threads fail closed before touching
the capability fields. The owner is fixed even though the gate's older
`main_thread` field is assigned later in its first entry. With no channel setting,
concurrent callers publish only ABSENT, retaining default thread behavior.
