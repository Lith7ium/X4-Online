# Independent Linux native client (internal)

`tools/dev/authority_client_native.py` keeps one authenticated pinned-TLS offer
connection alive through verified download, private-profile X4 load, marker/pause
observation, cooperative claim and server-directed pause/resume polling. The main
thread owns X4 and the client owner. A joined background thread serves TLS only.
No local server or coordinator is constructed. The staging-only CLI is unchanged.

A bounded native Linux observation passed on 17 November 2026: downloaded
checkpoint load, inspected marker, cooperative admission and one confirmed
server-directed resume/pause cycle. The server engine was simulated and TLS
was local. See the [evidence and limits](../reports/AUTHORITY-NATIVE-CLIENT-20261117.md).

```sh
python tools/dev/authority_client_native.py --internal-native-client \
  --game '/path/to/X4 Foundations' --display :1 --out .local/new-native-client \
  --host SERVER --port 4433 --fingerprint CERTIFICATE_SHA256 \
  --shared-key-file /private/key.hex --file-token-file /private/token.hex --slot 1 \
  --native-library /private/x4lan_net.so --native-library-sha256 LIBRARY_SHA256 \
  --timeout 600 --active-seconds 60 --keepalive-interval 5
```

Requires the pinned Linux executable, bubblewrap, an existing local X11 display,
readable `XAUTHORITY`, Steam identity and an explicitly hash-pinned existing native
UDP library. It never builds/downloads executable code. Secret-file formats match
the staging CLI. Keepalive requires matching server support and an interval below
its idle timeout. The output must be new and inside this checkout's `.local`.
The entire offered download/copy finishes before X4 starts; native save and probe
files are mounted read-only. Normal X4 profiles are never mounted writable.
The owner's copy operation also verifies the staged save. Do not repeat that
state transition or change the verified file's metadata before admission;
the claim checks its complete fingerprint, including change time.

A retained checkpoint may require its archived saved-state MD script. Only when
independently verified, supply `--archived-identity-fixture FILE`,
`--archived-identity-fixture-sha256 SHA256` and `--expected-content-sha256 SHA256`.
The generated private `content.xml` must match that pin. Exactly the checked script
bytes are copied/protected. No remote mod fetching or fixture UI observation is
added. The server/harness owns checkpoint provenance and content compatibility.
The expected checkpoint marker is never injected into the native configuration.

Success requires ordered ticket-bound load-request, native inspected-marker and
observed-pause receipts, accepted cooperative claim, at least one confirmed
server-directed native control, valid final evidence and confirmed owned cleanup.
Results expose separate server pause/resume confirmation counts, admission state,
fixed failure phase/type/code, fixture installation and cleanup failures. An
accepted claim alone is not session success. `exact_loaded_file_proven` remains
false. This does not establish playable multiplayer, Windows or Internet behavior.
Increase `--active-seconds` for a later explicitly authorized bounded session;
Ctrl-C stops only owned processes. Uncertain native operations are not retried.

Owned X4 cleanup finishes before client/TLS release and lock removal. Cleanup
failure prevents success and retains the private lock when cleanup is uncertain.
Downloaded/partial files and private logs remain for inspection; outputs are never
automatically deleted, reused or loaded into a normal profile.

An additional private playback path is documented in
[Buffered client playback](AUTHORITY-CLIENT-PLAYBACK.md). It requires an explicit
pinned configuration and a Python driver callback; the default CLI above remains
load/control only. Use a current, independently smoke-tested native UDP library:
a digest pin alone does not establish the required `socket.pending` capability.
See [the playback integration evidence](../reports/AUTHORITY-CLIENT-PLAYBACK-20261117.md)
for the failed attempts and bounded one-ship success with a private motion-control
intervention; these are not a passed gameplay test.
