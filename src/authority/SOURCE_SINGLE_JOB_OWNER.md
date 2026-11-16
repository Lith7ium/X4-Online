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
client delivery, Windows, Internet or gameplay is established by them. The bounded source-to-client diagnostic is described in
[its result record](../../tools/dev/AUTHORITY-SOURCE-TCP-PAIR.md); this module
is not a complete multiplayer path.

### Private source session for the TCP diagnostic

`tools/dev/authority_source_single_job_install.py` stages a separate, explicitly
opted-in source extension in a private profile. Its session runs from the
existing checkpoint-load owner's single `onUpdate`; it opens distinct local UDP
sockets for source control and source-job IPC. A control resume is accepted
only once and only after the source owner has handled the correlated `GO`.
The supervisor must authenticate both sockets against the owned X4 process,
check the job peer again while the bridge is in use, and request resume only
after receiving `GO_READY`. A transition state printed by this owner is a
sample, not a complete record: states can change between updates.

The registry is attached to the staged save using the historical script bytes;
its in-memory enrollment is part of this isolated test. The intended candidate
is one selected new registry entry resulting from a job activation. Such an
activation does not establish that a ship was born. The dynamic descriptor is
not an atomic snapshot and its sector identity has not been proved across
processes. An existing entry, an unexpected queue head, a missing client-sector
witness, a timeout, or a failed guard cannot be counted as successful delivery.

`tests.test_authority_source_single_job_install` exercises installer isolation,
the control ordering, and the actual session with the actual source owner, IPC
and gate; the latter test still simulates the host, MD, descriptor, transport
and X4 ABI. These tests do not demonstrate a real source-to-client transfer.
The diagnostic retains synthetic session/checkpoint admission and an
explicit client creation seed; it is not a Windows, Internet or gameplay test.
