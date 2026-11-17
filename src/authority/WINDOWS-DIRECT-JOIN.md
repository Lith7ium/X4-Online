# Windows direct-join preparation

The target is a Windows X4 client joining the Linux host's persistent X4
universe directly over the Internet. There is currently **no integrated Windows
authority launcher or installer**. The pieces below are development inputs;
they do not yet let a player join, fly, trade or fight on that server.

## Pieces available

The earlier LAN checkout, `work/x4-playtest7`, contains
`distribution/windows_setup.ps1`: Steam library and build discovery, a
separate test profile, reparse-point checks, staged mod installation, backups
and rollback. Its `Start-TestGame` requires an empty profile and starts a new
creative game; its connection check speaks the old UDP relay protocol. It is
not an authority-server installer. The earlier Windows seed harness in
`work/x4-primary-review-pr22/dev/native_seed_windows_test.py` stages one verified
seed and records restoration information, but targets the old LAN session. Its
optional name-wide `taskkill /IM X4.exe` must not be reused to manage another
person's running game. Reuse discovery, ownership records and reversible
staging selectively; keep existing player profiles and saves intact.

`experimental_tls_tunnel.py` supplies a pinned, encrypted direct client
tunnel for the current authority control and file TCP services. A Windows
Python-under-Wine loopback experiment exchanged data on both channels, and a
separate native Linux/Linux diagnostic loaded a checkpoint through the tunnel.
Neither result establishes a native Windows X4 client or an Internet session.
See [tunnel configuration and evidence](EXPERIMENTAL-TLS-TUNNEL.md).

`experimental_client_owner.py` can request an offer, download and stage the
checkpoint, accept correlated load/marker/pause observations supplied by its
caller, and hand the control connection to a participant adapter. The client
listeners of the TLS tunnel can supply its control and file endpoints. These
observations are caller assertions, not independently authenticated X4 events.
The owner has no Windows game-process or launcher integration. The Windows
fixture overlay in `experimental_windows_fixture_overlay.py` is limited to a
specific diagnostic checkpoint and does not start X4 or provide that supervisor.
See [client load observations](CLIENT_LOAD_BARRIER.md).

## Required connection work

1. Build a Windows session supervisor around the existing client owner and
   TLS client. It must start and monitor the tunnel, pass its loopback ports to
   the owner, and handle the separate file-service credential. A tunnel alone
   is not a game session.
2. Adapt the LAN installation/discovery and rollback code for a fresh,
   exclusively owned authority test profile and extension view. Verify game,
   enabled content and the offered checkpoint before staging. Never delete or
   overwrite an existing save to make room; retain recovery information for
   owned changes. Do not launch the old `Start-TestGame` unchanged.
3. Bind real Windows X4 load, checkpoint-marker and pause observations to the
   same owned process and outstanding offer, and connect the local X4
   participant controller to the owner. Keep it alive through admission and
   disconnect. Establish process and profile ownership rather than assuming
   an executable name or a path ending in `45841` proves ownership.
4. Install and validate the Windows native network module and Lua bridge in
   that authority view. Existing Windows crossbuild and synthetic tests do not
   establish that the module loads in Windows X4 or can drive a participant.
5. Integrate server-side join/pause/save behavior and player/ship replication;
   the diagnostic fixture and its two ships are not a general playable world.
   Test actual Windows/Linux joining on separate machines and the direct
   Internet route before claiming either works.

The direct client tunnel's existing explicit PowerShell command is documented
in [the tunnel notes](EXPERIMENTAL-TLS-TUNNEL.md#example-setup). It uses a
verified server certificate fingerprint and a shared key, starts only local
control/file forwarders, and does not install or launch X4. The server must
already provide the matching services, and router/firewall reachability remains
to be established for the real host.
