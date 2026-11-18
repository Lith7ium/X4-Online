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
- A separately verified Windows network DLL and its SHA-256. The client does
  not download or trust a DLL supplied by the server.
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
been tested. Existing session tests use real local TCP/UDP with simulated X4
responses. Neither is evidence that this assembled command starts Windows X4,
loads the right profile on Windows, completes Internet admission, or supports
the user's shared-world gameplay goal. A native Windows run is still required.
