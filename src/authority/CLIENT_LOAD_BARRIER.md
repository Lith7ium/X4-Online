# Experimental client load observations

`lua/client_load_barrier.lua` and `lua/x4_client_load_engine.lua` are opt-in
building blocks. Loading them registers nothing and starts no X4 action. No
launcher, process supervisor or network session currently uses them.

For an isolated experiment, a trusted supervisor must create a fresh, private,
immutable UI configuration before starting one exclusively controlled X4
process. It supplies a unique `attempt_id` and the exact coordinator offer
fields (`world_epoch`, `connection_handle`, `baseline_id`, `load_generation`,
`checkpoint_id`, `sha256`) and the already staged `save_###` slot as
`ticket`. The complete ticket is copied by the component. The owner must
refresh the save list with the adapter and wait until it is loaded. Calling
`begin()` in the start menu emits `load_requested` and calls X4 `LoadGame`.
The event precedes the call, so it is only an attempt, never success.

X4 rebuilds Lua after `LoadGame`. The experiment must re-read the same protected
configuration and explicitly call `observe_pause()` in the new UI. Once it sees
a valid player outside the start menu, the component requests pause at most once
and waits until X4 reports the game paused. It then emits `pause_observed` and
the configured ticket. It never unpauses. The supervisor, not Lua, must verify
that the configuration remained unchanged, both ordered events came from the
same still-owned process, the events match the outstanding offer and attempt,
and no other load or game activity interfered. It must reject old or duplicate
events. A pause observation by itself does not show that `LoadGame` succeeded,
which file X4 consumed, that no simulation occurred before the pause, or that
the loaded universe matches the checkpoint.

No authenticated event transport or cross-reload supervisor has been implemented
here. In particular, neither event may currently be used as a `mark_loaded`
confirmation. A real integration still needs controlled save staging, process
and event fencing, ordered observations, client compatibility checks, a policy
for already connected clients, and a verified resume protocol. The configuration
approach is limited to an isolated process started for one attempt; it does not
design dynamic rejoining of a running client.

`tests/test_authority_client_load_barrier.py` runs Lua with test doubles only.
A separate isolated Linux X4 run combined this barrier with a localhost download;
see [the native experiment](../../docs/AUTHORITY-CLIENT-DOWNLOAD-LOAD.md). It
does not establish Windows behavior or actual client admission.

## Experimental single-thread client owner

`experimental_client_owner.py` composes the existing remote load client with
`ExperimentalTCPParticipantClient` on one owner thread. After the server accepts
the load claim, it transfers the same connected socket once to the participant
adapter. The owner validates the known participant prerequisites before making
the claim, closes the socket on failure or explicit close, and rejects calls
from other threads. If admission succeeds but the later handoff fails, the
server may already consider the client admitted; the caller must treat that
outcome as uncertain and must not retry the claim automatically.

The caller still owns transport authentication, private staging paths, the X4
process and its identity, ordered load/marker/pause observations, and a bounded
pause/resume controller. Observations passed to the owner are trusted caller
assertions, not independently verified game events. While waiting for them, the
caller must pump the load connection often enough when keepalive is enabled.
There is no Windows process or X4 integration, no authenticated X4 event
channel, and no proof of which file X4 reads. The owner has no production
launcher integration and does not establish gameplay. Focused local tests use
real wire and file-service components with simulated X4 observations and
controller results; they do not establish native Windows or Internet behavior.
