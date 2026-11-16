# Experimental single held source job owner

`lua/source_single_job_owner.lua` joins the existing saved-registry host,
running read-only descriptor probe and source IPC/gate for exactly one selected
activation queue entry. `new_x4` binds the actual local X4 callbacks and FFI
adapters, but installs no extension, opens no socket, launches no process and
registers no `onUpdate`. A private supervisor must supply one connected
`x4lan_net` socket, an existing exclusive update owner, the X4 modules and a
strict external process/profile/session guard; it must fence the process and
all clients on any uncertain outcome. The existing source queue and registry
consumers must be exclusively reserved. The external guard and PID/socket
checks are assertions and samples, not continuous process control.

The initial game must be paused with its saved registry already attached to the
same epoch and exactly `index - 1` entries; the host does not reset it. The
owner accepts only `sequence=1`, the specified index and classification
`new_registry_entry`. Other entries fail the experiment before delivery. This
classification only means a registry entry was allocated: activation does not
prove a ship was born or absent from any client. In particular this owner must
not be used to infer that creating a replica is generally safe. The source
registry's Enroll is attempted before this classification is available.

The owner sends one `S|lease|attempt|HELLO|epoch|generation`, then requires
`P|lease|attempt|BOUND|epoch|generation` before touching the host. The
supervisor must pin the actual UDP peer to the intended owned process before
sending BOUND. After saved-registry and fresh-queue attach, the owner sends
`S|lease|attempt|ATTACHED|epoch|generation`. The supervisor then takes exclusive
ownership of the pinned Python socket, sends `P|lease|attempt|GO|epoch|generation`
and waits for `S|lease|attempt|GO_READY|epoch|generation` before resuming X4.
Only after this exchange may it hand the socket to `ExperimentalSourceJobBridge`.
A single Python reader must own the socket throughout. The X4 binding checks a
constant sampled game time while paused, requires time to have advanced before
the selected event is read, and then requires a running game with monotone
sampled time through REARM. These checks cannot detect changes between samples.
A lost, foreign or unexpected datagram faults this disposable attempt. The native
UDP library limits each datagram to 768 bytes; larger membership messages fail
rather than establishing the IPC adapter's theoretical maximum of 16 clients.

Once the selected queue head has been enrolled and held, the owner starts one
independently correlated running descriptor read. The descriptor's fields and
position are separate non-atomic observations. Its sector macro is not a
proven portable, unique sector identity and its pose does not include velocity
or complete ship state. No local actor or sector handle is sent to Python.
The source IPC snapshots the descriptor and requires receipts from every
admitted TCP peer before dispatching the held MD Ack. A callback records the
actual MD `Acked`; only after that callback returns does the owner notify the
IPC adapter to emit `SOURCE_ACKED`. While waiting for `REARM`, the owner does
not tick the host or take another queue head. The experiment ends after REARM;
the game may still have queued or lost other events, and bounded queue overflow
or any guard, response, identity or timeout failure fences the whole run. No
retry or recovery is safe without separately reconciling possible side effects.

`tests/authority_source_single_job_owner.lua` exercises the actual host,
registry probe, source IPC and delivery gate with simulated MD, descriptor,
network and two clients. It checks peer binding, rejection of an existing
registry entry, no source Ack after only the first client, the separate MD Ack
and no second head before REARM. Existing host fake-ABI tests also check the
new optional callback guard. These are offline tests; no native X4 source,
client delivery, Windows, Internet or gameplay is established by them. An
installer, process supervisor and full end-to-end native connection remain
separate work; this module must not be reported as a complete multiplayer path.
