# Windows fixture client diagnostic

`authority_windows_fixture_client.py` composes the existing encrypted client
connection, checkpoint transfer, fixture overlay, Windows X4 process owner and
observed participant session. It is an opt-in developer diagnostic. It does
not install a playable multiplayer client, replicate ships, or send player
actions. A successful result records a bounded load/admission observation and
owned-process cleanup, not gameplay or Internet acceptance.

## Prerequisites

- Windows with Python 3.11 or later, logged-in Steam ready for direct X4
  startup, and the repository's pinned Windows X4 9.00 executable. The command
  does not change Steam registry settings.
- An isolated workstation with no other X4 running. Do not start another X4 or
  modify the test directories during the diagnostic. These are cooperative,
  sampled ownership checks, not an atomic sandbox against local writers.
- The current user's actual Documents/Egosoft/X4 root must exist and its
  `45841` child must be absent. Existing profiles are never removed or reused.
  The current fixture overlay requires an ASCII save path; redirected
  Documents is resolved through Windows, but reparse-point paths are refused.
- Two absent output containers under existing directories. The view container
  must be on the game drive. The workspace creates a `game` view inside it;
  official game files are linked and third-party installed mods are omitted.
- A Windows network DLL built from the current `src/native/net.c`, with its
  independently verified SHA-256. See the build step below. The historical DLL
  in `src/lockstep/base/native/` lacks the required `monotonic` function and
  cannot be used for this client. The client does not download or trust a DLL
  supplied by the server.
- A running authority server with the existing load/participant protocol,
  keepalive enabled, and a marked checkpoint containing the two identity
  fixture ships. An arbitrary personal save is not suitable.

Expose the server's existing loopback control and file services through the
[existing TLS server bridge](../../src/authority/EXPERIMENTAL-TLS-TUNNEL.md#example-setup).
The recovered Linux supervisor publishes their addresses and file-service
token in its private `endpoint.json`. Use those actual service ports when
starting the bridge. Its public host/port, verified certificate fingerprint,
shared key and file-service token must reach the client through a trusted
channel. This diagnostic does not configure a router or firewall, and this
combined route has not yet been validated with Windows X4.

## Build the current network DLL

Use the existing builder with Zig 0.15.2 and a new output directory. It can
cross-build the Windows DLL on Linux; it does not need X4 or modify an installed
game. For example, from the checkout in PowerShell:

```powershell
python src/native/build.py --zig C:\Tools\zig\zig.exe `
  --platform windows --out C:\X4Test\network-build-01
(Get-FileHash C:\X4Test\network-build-01\x4lan_net_64.dll -Algorithm SHA256).Hash.ToLowerInvariant()
```

Use that built file as `--network-dll` and its digest as
`--network-dll-sha256`. When transferring a build to another computer, compare
the received file's digest with the value obtained from the trusted build
machine. Computing a digest of an arbitrary downloaded DLL does not verify its
origin. The explicit digest is an integrity check, not an API/version check.

The current source cross-build passed on Linux with Zig 0.15.2. Static PE
inspection found the Lua entry point and Windows performance-counter imports;
loading it inside native Windows X4 remains untested. Details and the local
artifact digest are in the [build record](../../reports/AUTHORITY-WINDOWS-NETWORK-BUILD-20261118.md).

## Invocation

Create a private connection file outside the new output containers. Replace
every placeholder; credentials are deliberately not command-line arguments:

```json
{
  "server_host": "HOST_NAME_OR_PUBLIC_IP",
  "server_port": 47000,
  "server_fingerprint": "64_LOWERCASE_HEXADECIMAL_CHARACTERS",
  "shared_key": "64_LOWERCASE_HEXADECIMAL_CHARACTERS",
  "file_token": "32_LOWERCASE_HEXADECIMAL_CHARACTERS",
  "file_slot": 1
}
```

From this checkout, in PowerShell, use absolute paths appropriate to that
machine (the directories below are examples, not created prerequisites):

```powershell
python tools/dev/authority_windows_fixture_client.py `
  --isolated-fixture-test `
  --connection-file C:\X4Test\connection.json `
  --game 'D:\SteamLibrary\steamapps\common\X4 Foundations' `
  --view-container D:\X4Tests\client-view-01 `
  --out C:\X4Test\client-run-01 `
  --network-dll C:\X4Test\x4lan_net_64.dll `
  --network-dll-sha256 VERIFIED_DLL_SHA256 `
  --timeout 600 --observe-seconds 30 --keepalive-seconds 5
```

The overall deadline includes preparation and loading. The observation window
starts only after admission. The client handles server-issued pause/resume
commands during that window; it does not independently request resume. The
default local participant response timeout is 30 seconds; the matching server
must allow more time for its response. The keepalive interval must fit the
server's configured idle timeout.

At the end, the diagnostic terminates only its owned X4 job, checks the final
log and closes its client connection. The server remains responsible for
processing departure and persisting the world. Client success does not prove
that the server completed that save. On a fault or Ctrl+C the same owned
cleanup is attempted and the command exits unsuccessfully. An uncertain stop
is not reported as successful cleanup.

The workspace retains its profile, downloaded save, view and log for inspection.
Initial display/content settings are checked before launch; X4 may rewrite
those disposable settings during its lifetime. Immutable overlay and staged
save checks use file identities and metadata during polling, not continuous
byte-by-byte hashing. Concurrent local writers remain outside this diagnostic's
isolation assumptions.
Only the pinned overlay configuration containing the local lease is removed
after confirmed process cleanup. Partial installations or uncertain cleanup
retain their private configuration too. There is no automatic retry, recursive
deletion, profile restoration or reuse. The CLI reports error type and source
location without echoing exception text or credentials. Inspect the retained
artifacts before arranging any subsequent test.

## Validation boundary

Nine filesystem tests use real temporary files with Windows commands, profile
lookup, executable verification and view construction simulated. Twelve
lifecycle tests and five CLI tests cover orchestration/configuration with
Windows/X4 doubles. Actual NTFS junction handling and ACL inheritance have not
been tested.

One additional assembled integration test passed using the actual workspace,
overlay installer, client owner, log parser and session lifecycle over real
local TLS, file transfer, TCP and UDP. It checks the staged bytes, installed
configuration, correlated claim, a confirmed resume command and config removal
after the simulated process stops. The control peer is scripted; Windows APIs,
game-view creation, Windows path rendering and X4 are simulated. The synthetic
checkpoint is not a game save, and the dummy DLL and game Lua are not executed.
This verifies client wiring, not the actual server's admission/save policy.

None of these checks establishes that this assembled command starts Windows
X4, loads the right profile on Windows, completes Internet admission, or
supports the user's shared-world gameplay goal. A native Windows run is still
required.

## Remaining motion integration

The observed session can accept an optional motion consumer through the existing
TCP owner. This CLI does not supply one. Reuse the existing
`ExperimentalParticipantMotionIPC` and Lua motion owner when wiring the native
path; do not create a second TCP reader. The overlay still needs the matching
saved-registry/motion scripts and their lifecycle, including STOP before X4 exit.

The Linux peer validator reads `/proc` and is not portable to Windows. No Windows
equivalent is implemented yet. The existing `WindowsX4Process` owns a live process
handle/job and exposes its PID; reuse that owner when checking the local motion
socket. Microsoft's
[UDP owner row](https://learn.microsoft.com/en-us/windows/win32/api/udpmib/ns-udpmib-mib_udprow_owner_pid)
provides the bound local address, port and owning PID, but no remote endpoint.
Consequently, a validator using that table must document its narrower observation
and cannot claim the Linux connected-tuple check. API and real Windows behavior
still need validation before enabling movement in this command.
