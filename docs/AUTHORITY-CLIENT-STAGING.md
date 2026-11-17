# Independent client checkpoint staging

`tools/dev/authority_client_stage.py` uses the existing pinned TLS tunnel and
client owner to request an offer, download it into a new directory, verify its
bytes and disconnect. It sends no load observation, claim or activation. A
successful result explicitly has `admitted: false`. This is internal groundwork,
not a playable client or proof of Windows/Internet/X4 operation.

Example, using the repository's Python environment:

```sh
python tools/dev/authority_client_stage.py \
  --host SERVER_ADDRESS --port 4433 --fingerprint SERVER_CERTIFICATE_SHA256 \
  --shared-key-file /private/server-key.hex \
  --file-token-file /private/file-token.hex --slot 1 \
  --out /private/new-checkpoint-directory --timeout 120
```

The shared-key file contains 64 lowercase hexadecimal characters (32 bytes); the file-token
file contains 32 lowercase hexadecimal characters. A trailing LF or CRLF is allowed; extra content is refused.
Credentials are read from files. The shared TLS key stays in the parent; only the
file token reaches the owned child through stdin. Neither is passed as a command
argument. Output contains fixed status/error categories and
checkpoint metadata; it never includes exception text or credentials. Obtain
the certificate pin and credentials through an independently trusted channel.
Optional `--keepalive-interval` requires the server's matching keepalive support.

Python 3.11 or newer is required. The portable async API is `stage_client_connection` in
`src/authority/experimental_client_connection.py`. It owns two ephemeral IPv4
loopback listeners and the TLS client bridge. A separate subprocess opens fresh
TCP connections and owns the synchronous `ExperimentalClientOwner` until close.
There are no inherited application descriptors, Unix sockets or `/proc` checks.
The original transport/protocol is unchanged.

The caller exclusively controls the output parent throughout the operation.
Existing output paths are refused. Failed/cancelled attempts may leave a new
partial or verified directory for inspection: it is never automatically deleted,
retried, reused or loaded into X4. This tool does not access normal X4 profiles.

The parent enforces the overall monotonic deadline. The child receives a bounded
remaining-duration budget; parent timeout also terminates the child. Cancellation
awaits cleanup before returning cancellation, including repeated cancellations.
Cleanup requests TERM, waits two seconds, requests kill if necessary, and waits
two seconds again before reporting failure to reap. It then closes TLS resources.
No software can guarantee immediate cleanup of a process stuck in uninterruptible
kernel I/O; cleanup failures are reported and must not be interpreted as success.
