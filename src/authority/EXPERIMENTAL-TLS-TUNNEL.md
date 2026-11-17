# Experimental direct TLS tunnel

This optional transport connects the existing control and file TCP services to
local client ports over one direct, pinned TLS endpoint. It is an isolated
transport experiment, not a complete X4 host or Windows launcher. It has only
been exercised over local sockets with simulated participants and echo backends.
A native Windows client, an Internet route, X4 gameplay and save recovery remain
unverified.
For the previous tunnel protocol version 1 (commit `835a083`), Windows Python
3.14.8 under Wine exchanged data successfully with a Linux loopback peer on
both service channels. A subsequent version 2 probe used Windows Python 3.14.8
under Wine against a Linux loopback server with echo backends. Both service
channels exchanged data before and after seven seconds of application inactivity
with a two-second idle timeout. The local result is recorded in
`.local/windows-python-tls-wine-01/result-v2.log`. Neither probe exercised native
Windows, the Internet or X4.

The server listens on an explicitly chosen IPv4 address. Each connection uses
TLS 1.2 or later, then a shared 32-byte random key and a fixed service selector.
The client checks SHA-256 of the exact DER-encoded server certificate before it
sends the key. The server connects to its configured `127.0.0.1` backend only
after authentication; no remote destination or port can be requested. Tunnel
protocol version 2 adds internal ping/pong frames and requires version 2 at both
ends; it does not interoperate with the earlier version 1 tunnel. Replacing
the certificate changes the fingerprint and requires a new trusted fingerprint
on every client. Pin verification replaces normal CA, hostname, and certificate
expiry checks. Transfer the fingerprint and key through a trusted channel.
The fingerprint is public; the shared key and private key must remain private.
Use an independently generated random key, not a memorable password.

Both client listeners bind only to `127.0.0.1`. Other local processes may still
connect to them; the tunnel does not authenticate local processes. The backend
file service sees the server tunnel as `127.0.0.1`, not the remote IP, and must
allow loopback. All authorized tunnel users share access to the configured
services; this does not establish player identity or per-player authorization.
Secure the server private-key and shared-key files using the operating system's
file permissions. Protect client hosts too. No secret is passed as a process
argument or deliberately written to logs.

The default limit is eight active connections per tunnel; the CLI options
`--max-connections` and `--idle-timeout` select other bounded values. A player may need both
a long-lived control connection and a simultaneous file connection; provision
at least two slots per concurrent player. Excess accepted connections wait at
most one per listener for a slot; additional connections wait in the bounded
socket backlog. TLS handshake, authentication and backend connection each have
a 10-second deadline. During application inactivity, tunnel peers exchange
internal heartbeat frames with a fresh random challenge. Only valid received
frames count as peer progress; a missing peer closes the connection after the
configured idle timeout (300 seconds by default). Heavy backpressure can also
reach this timeout. Frames carry at most 64 KiB; EOF is signalled independently in
each direction so TCP half-closes do not truncate the opposite stream. These
limits are experimental and do not replace admission, game state or transport
identity checks.

## Example setup

From the checkout on Linux, create private material in a private directory. This
example uses OpenSSL for material creation; the tunnel itself uses Python's
standard library. Never use the test certificates or test keys in production.

```sh
umask 077
openssl req -x509 -newkey rsa:3072 -nodes -keyout server-key.pem -out server-cert.pem -days 365 -subj /CN=x4-server
openssl rand -hex 32 > shared-key.txt
openssl x509 -in server-cert.pem -outform DER | openssl dgst -sha256
```

Give the client the 64 lowercase hexadecimal fingerprint and a protected copy of
`shared-key.txt` over a trusted channel. Start existing server-side control and
file services on loopback first. Choose free ports and use the actual interface
address and service ports in place of these examples:

```sh
PYTHONPATH=src python -m authority.experimental_tls_tunnel server \
  --listen-address 0.0.0.0 --listen-port 47000 \
  --certificate server-cert.pem --private-key server-key.pem --key-file shared-key.txt \
  --control-port 47001 --file-port 47002
```

In Windows PowerShell, from a checkout with Python 3.11 or later, start the
client tunnel with the server's reachable public host, the previously verified
fingerprint, and the same key file:

```powershell
$env:PYTHONPATH = 'src'
python -m authority.experimental_tls_tunnel client `
  --server-host SERVER_HOST --server-port 47000 --fingerprint VERIFIED_FINGERPRINT `
  --key-file shared-key.txt --control-port 47101 --file-port 47102
```

Client programs then connect to control port `127.0.0.1:47101` and file port
`127.0.0.1:47102`. Stop the tunnel with Ctrl+C. Exposing the server port through
the host firewall/router and the actual client-owner integration remain separate
tasks; this example does not modify either. The file-service token and existing
load/participant checks remain required. TLS alone does not make the experiment
safe for arbitrary users or prove that X4 state is synchronized.

For embedding, `await start_server(...)` and `await start_client(...)` take
already-listening sockets and return `RunningTunnel`. The owner must monitor
`await tunnel.wait()` and call `await tunnel.close()` during shutdown. A listener
failure closes all of that tunnel's listeners and connections and raises a
sanitized `RuntimeError` from `wait()`.
