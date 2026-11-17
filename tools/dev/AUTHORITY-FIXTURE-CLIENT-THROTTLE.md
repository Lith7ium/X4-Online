# Disposable fixture client throttle impulse

The default-off Lua owner and MD cue are uninstalled building blocks, not a
running experiment. They make no network calls, create no player or ship, do
not save, and do not own an X4 update loop. The caller must install both in a
disposable private client, bind event callbacks and `tick` to the existing
owner, and independently guard the owned process, profile, loaded checkpoint,
fixture grant, active seat, running game, deadline and cleanup. Callbacks must
be trusted and observational except for the one dispatch. Never load the cue in
a normal profile or leave a failed experiment running.

The cue checks the saved four-entry fixture registry in both directions, epoch,
ship, sector, local owner and all player-control references before setting the
current player ship throttle to 0.2. After one game second it repeats these
checks and requests throttle zero only for the same controlled fixture. It
never teleports. The MD events acknowledge that the respective MD action
returned; they do not prove the engine actually applied it or that the ship
stopped. If the seat or guard changes or a receipt is lost, the caller must
stop the owned X4 process without retrying; a delayed MD cue may still exist.
Game pause, a wedged X4 or a terminated supervisor can prevent the delayed
stop, so the caller must enforce the real-time deadline and stop its disposable
process when the result is uncertain. No callback or check is atomic with the
engine action, and there is no collision-clearance or stable-sector proof.

The Lua owner requires a distinct 32-hex epoch and nonce, slot 1 or 2, a
3–15 second real-time timeout and explicit clock, guard, dispatch and log
callbacks. A successful result requires the ordered correlated start and stop
receipts and valid guards; `start_attempted` means dispatch began, not that X4
received it, and `effect_uncertain` remains true until the correlated stop
receipt. STARTED and STOPPED log lines precede the final guard and are not
standalone success evidence. A stop receipt is not proof of stationary movement
or human input.
The Lua owner must be constructed and started at most once per private X4
process; loading it again cannot safely retry an uncertain attempt.

This intentionally stimulates native flight rather than testing human or XTEST
input. An actual source movement and its receipt at the server require separate
observations tied to the same active participant and increasing sequence. No
X4 launch, native run, schema evaluation, Windows behavior or multiplayer
success follows from this component or its synthetic tests.

## Private fixture-source integration

The retained fixture-client installer accepts an explicit `throttle=True`
setting. It installs the cue, owner and driver into that private profile and
adds their paths to the existing protected-file checks. The existing source
update owner drives the optional driver only after the seat is ready and its
source session is running. No throttle action occurs merely by enabling or
loading the module: the driver announces READY on its separate loopback socket
and waits for the supervisor's one correlated GO.

After the supervisor has separately observed a valid participant baseline,
it may call `participant.pulse_fixture_throttle(process=..., guard=...,
running=..., pump=..., timeout=15)`. The process identity must equal the
client X4 pinned at admission; the caller must keep the same grant, client,
server, session and resource guards live throughout. The socket peer must
belong to that process. The single-use call returns only dispatch, STARTED and
STOPPED receipt evidence. `ThrottleUnconfirmed` exposes `attempted`,
`started` and `stopped`; a send attempt without an independently validated
result is uncertain and the caller must stop the owned client rather than
retry. The private socket and credentials are owned by the participant and
cleaned/redacted with its existing lifecycle. Socket identity, process and peer
checks are sampled rather than atomic; exclusive socket/FD ownership and
serialized supervisor use are required.

Neither the `READY`/`GO` handshake nor the throttle receipts establish a
changed position. The supervisor must compare later validated source samples
against its earlier baseline, including participant and sector identity, and
correlate any subsequent server write with that specific changed sample.

The STOPPED receipt additionally carries `stop_game_time`, read from this same
client's `GetCurrentGameTime()` after the correlated MD stop callback, bounded
and guarded before and after the read. SAMPLE2 `source_time` is the same game
clock read after the corresponding local position getter. Requiring a later
SAMPLE2 time establishes a later timestamp. Claiming its getter also ran after
the stop relies on X4 executing these Lua callbacks serially; the timestamp by
itself does not prove this ordering under concurrent callbacks. The clock says
nothing about collision clearance, human input, or cross-process frame parity.
