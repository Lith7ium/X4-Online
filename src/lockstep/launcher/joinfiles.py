"""Join file service: a hot joiner (x4ls join without --arm-at) fetches the join save and the join package of a running
x4ls play session (--open K) from the host over TCP. Standard library only.

Protocol 1, one request per connection: an ASCII line, then raw bytes.
  joiner -> host  X4JF|1|<slot>|<nonce>|<name>|<offset>|<mac>\\n
                  nonce: 16 hex digits, fresh per request; mac: HMAC-SHA256 hex of 'X4JF|1|<slot>|<nonce>|<name>|<offset>'
                  keyed with the session token (the token itself never crosses this link)
  host -> joiner  OK|<size>|<sha256>\\n and then the bytes from <offset> to <size>, or NO|<reason>\\n
Names: j<T>.xml.gz and j<T>.x4join, and only what the host offered: a join's two files once the relay's SAVED notice named
them and they matched their hashes (hotjoin.HostJoins). A wrong mac, a nonce seen before, an unknown name or an offset past
the end is NO; so is a source address the session does not allow. A fetch resumes a partial download (<dest>.part) from its
length and keeps the file only when the size and SHA-256 match the host's, which must match the hash the caller expects
(the relay's NGJOINSTATE names the package's)."""
import hashlib
import hmac
import math
from pathlib import Path
import re
import secrets
import socket
import socketserver
import threading
import time

PROTOCOL = 1
NAME = re.compile(r'j\d{1,7}\.(?:xml\.gz|x4join)')
HEX64 = re.compile(r'[0-9a-f]{64}')
LINE_MAX = 512
CHUNK = 1 << 20
REFUSE_DRAIN_S = 2.0    # a refusal waits this long at most for the client to close (a graceful close, not a reset)
TIMEOUT_S = 60         # a stalled connection (either side) gives up after this long without progress
CONNECTIONS_MAX = 8     # concurrent downloads the host serves
NONCES_MAX = 4096


class FetchError(Exception):
    pass


class FetchDeadline(FetchError, TimeoutError):
    """The caller's monotonic transfer deadline was exhausted."""


def _remaining(deadline):
    if deadline is None:
        return None
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError('invalid transfer deadline')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise FetchDeadline('join-file transfer deadline expired')
    return remaining


def _connect(host, port, timeout, deadline):
    if deadline is None:
        return socket.create_connection((host, port), timeout=timeout)
    # getaddrinfo may block outside Python's control. Once it returns, each
    # candidate gets only the time still available to the entire transfer.
    _remaining(deadline)
    addresses = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    last = None
    for family, socktype, proto, _, address in addresses:
        _remaining(deadline)
        conn = None
        try:
            conn = socket.socket(family, socktype, proto)
            conn.settimeout(min(timeout, _remaining(deadline)))
            conn.connect(address)
            _remaining(deadline)
            return conn
        except BaseException as error:
            if conn is not None:
                conn.close()
            if not isinstance(error, OSError) or isinstance(error, FetchDeadline):
                raise
            last = error
    _remaining(deadline)
    if last is not None:
        raise last
    raise OSError('no addresses found')


def mac(token, slot, nonce, name, offset):
    text = f'X4JF|{PROTOCOL}|{slot}|{nonce}|{name}|{offset}'
    return hmac.new(token.encode('ascii'), text.encode('ascii'), hashlib.sha256).hexdigest()


def request_line(token, slot, name, offset=0, nonce=None):
    nonce = nonce or secrets.token_hex(8)
    return f'X4JF|{PROTOCOL}|{slot}|{nonce}|{name}|{offset}|{mac(token, slot, nonce, name, offset)}\n'.encode('ascii')


def sha256_file(path, *, deadline=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            _remaining(deadline)
            block = f.read(CHUNK)
            _remaining(deadline)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


class FileService:
    """The host's side: serve the offered files to the session's allowed addresses (127.0.0.1 always)."""
    def __init__(self, token, bind='127.0.0.1', port=0, allow=(), slots=()):
        if not re.fullmatch(r'[0-9a-f]{32}', token):
            raise ValueError('the session token is 32 hex digits')
        self.token, self.allow = token, frozenset({'127.0.0.1', *allow})
        # An explicit slot set can include 1 for an authority server whose
        # local host is also a client. The legacy default remains 2..8.
        self.slots = frozenset(slots)
        self.offered, self.nonces, self.lock = {}, set(), threading.Lock()
        self.served, self.refused, self.active = [], [], 0
        self._transfers = {}  # accepted sockets mapped to their offered name
        service = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                service.handle(self.request, self.client_address)

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True
        self.server = Server((bind, port), Handler)
        self.port = self.server.server_address[1]
        self.thread = None

    def offer(self, name, path, sha=None):
        """Offer a file under name (checked against sha when given); returns (size, sha)."""
        if not NAME.fullmatch(name):
            raise ValueError(f'not a join file name: {name}')
        path = Path(path)
        digest = sha256_file(path)
        if sha is not None and digest != sha:
            raise ValueError(f'{path}: SHA-256 {digest[:16]}.. is not the announced {sha[:16]}..')
        size = path.stat().st_size
        with self.lock:
            self._withdraw_locked(name)
            self.offered[name] = (path, size, digest)
        return size, digest

    def _withdraw_locked(self, name):
        self.offered.pop(name, None)
        for conn, offered_name in tuple(self._transfers.items()):
            if offered_name == name:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass  # peer may already have disconnected

    def withdraw(self, name):
        """Withdraw an offer and interrupt its accepted, still-active transfers.

        Data already handed to TCP can still reach a peer; a completed download
        is not an admission confirmation and requires separate epoch fencing.
        """
        self.withdraw_many((name,))

    def withdraw_many(self, names):
        """Withdraw a set of names atomically with respect to new requests."""
        with self.lock:
            for name in names:
                self._withdraw_locked(name)

    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True)
        self.thread.start()
        return self

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def refuse(self, conn, address, reason):
        with self.lock:
            self.refused.append((address[0], reason))
        try:
            conn.sendall(f'NO|{reason}\n'.encode('ascii'))
            # Close gracefully: closing with the request still unread resets the connection, and on Windows the reset can
            # overtake the answer (the client then sees WinError 10053, not the reason). Half-close, then read what is left
            # until the client closes, for at most REFUSE_DRAIN_S.
            conn.shutdown(socket.SHUT_WR)
            deadline = time.monotonic() + REFUSE_DRAIN_S
            while (left := deadline - time.monotonic()) > 0:
                conn.settimeout(left)
                if not conn.recv(4096):
                    break
        except OSError:
            pass

    def handle(self, conn, address):
        conn.settimeout(TIMEOUT_S)
        if address[0] not in self.allow:
            return self.refuse(conn, address, 'address')
        with self.lock:
            if self.active >= CONNECTIONS_MAX:
                busy = True
            else:
                busy, self.active = False, self.active + 1
        if busy:
            return self.refuse(conn, address, 'busy')
        try:
            line = b''
            while not line.endswith(b'\n'):
                data = conn.recv(LINE_MAX + 1 - len(line))
                if not data or len(line) + len(data) > LINE_MAX:
                    return self.refuse(conn, address, 'request')
                line += data
            try:
                f = line.decode('ascii').rstrip('\n').split('|')
            except UnicodeError:
                return self.refuse(conn, address, 'request')
            if len(f) != 7 or f[0] != 'X4JF' or f[1] != str(PROTOCOL) or not f[2].isdigit() or not f[5].isdigit() or \
                    not re.fullmatch(r'[0-9a-f]{16}', f[3]) or not re.fullmatch(r'[0-9a-f]{64}', f[6]):
                return self.refuse(conn, address, 'request')
            slot, nonce, name, offset = int(f[2]), f[3], f[4], int(f[5])
            if not hmac.compare_digest(f[6], mac(self.token, f[2], nonce, name, f[5])):
                return self.refuse(conn, address, 'mac')
            minimum_slot = 1 if self.slots else 2
            if (self.slots and slot not in self.slots) or not minimum_slot <= slot <= 8:
                return self.refuse(conn, address, 'slot')
            with self.lock:
                replay = nonce in self.nonces
                if not replay:
                    if len(self.nonces) >= NONCES_MAX:
                        self.nonces.clear()   # bounded; a replay of a cleared nonce still needs the token's mac
                    self.nonces.add(nonce)
                entry = self.offered.get(name)
                if not replay and entry is not None and offset <= entry[1]:
                    self._transfers[conn] = name
            if replay:
                return self.refuse(conn, address, 'nonce')
            if entry is None:
                return self.refuse(conn, address, 'name')
            path, size, digest = entry
            if offset > size:
                return self.refuse(conn, address, 'offset')
            conn.sendall(f'OK|{size}|{digest}\n'.encode('ascii'))
            with open(path, 'rb') as source:
                source.seek(offset)
                sent = offset
                while sent < size:
                    block = source.read(min(CHUNK, size - sent))
                    if not block:
                        break
                    conn.sendall(block)
                    sent += len(block)
            with self.lock:
                self.served.append((address[0], name, offset, sent))
        except OSError:
            pass
        finally:
            with self.lock:
                self._transfers.pop(conn, None)
                self.active -= 1


OFFER_WAIT_S = 180   # the relay answers saved before the host has read the notice and hashed the files: 'name' is retried this long


def fetch(host, port, token, slot, name, dest, expect_sha=None, retries=5, progress=None, timeout=TIMEOUT_S, offer_wait_s=OFFER_WAIT_S, expect_size=None, *, deadline=None):
    """Download and verify, optionally bounded by an absolute monotonic deadline.

    DNS resolution, filesystem calls and user callbacks cannot be interrupted;
    the deadline is checked after they return. Partial files remain available
    for an explicitly requested retry, just as without a deadline. A filesystem
    operation can finish after the deadline: in particular, a verified target
    may exist even though the post-replace deadline check reports failure.
    """
    if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline)):
        raise ValueError('invalid transfer deadline')
    def budget():
        left = _remaining(deadline)
        return timeout if left is None else min(timeout, left)
    def sleep_bounded(delay):
        left = _remaining(deadline)
        time.sleep(delay if left is None else min(delay, left))
        _remaining(deadline)
    if not NAME.fullmatch(name):
        raise FetchError(f'not a join file name: {name}')
    if expect_size is not None and (type(expect_size) is not int or expect_size <= 0):
        raise FetchError('invalid expected file size')
    dest = Path(dest)
    part = dest.with_name(dest.name + '.part')
    dest.parent.mkdir(parents=True, exist_ok=True)
    last, attempt, offer_deadline = None, 0, time.monotonic() + offer_wait_s
    while attempt <= retries:
        _remaining(deadline)
        if attempt:
            sleep_bounded(min(2 ** attempt, 20))
        attempt += 1
        offset = part.stat().st_size if part.is_file() else 0
        try:
            with _connect(host, port, timeout, deadline) as conn:
                request = request_line(token, slot, name, offset)
                conn.settimeout(budget())
                conn.sendall(request)
                _remaining(deadline)
                head = b''
                while not head.endswith(b'\n'):
                    conn.settimeout(budget())
                    data = conn.recv(1)
                    _remaining(deadline)
                    if not data or len(head) > LINE_MAX:
                        raise FetchError('the host closed the connection before its answer')
                    head += data
                f = head.decode('ascii', 'replace').rstrip('\n').split('|')
                if f[0] == 'NO':
                    reason = f[1] if len(f) > 1 else '?'
                    if reason == 'name' and time.monotonic() < offer_deadline:
                        attempt -= 1          # not offered yet: wait for the host, without using up a retry
                        sleep_bounded(2)
                        last = FetchError(f'{name}: not offered by the host within {offer_wait_s} s')
                        continue
                    if reason in ('busy',):
                        last = FetchError(f'{name}: host busy')
                        continue
                    if reason == 'offset' and offset:
                        # The server rejects an oversized partial before sending
                        # its size. Discard it and retry from the beginning.
                        part.unlink()
                        last = FetchError(f'{name}: partial download exceeds the host file')
                        continue
                    if reason == 'name':
                        raise FetchError(f'{name}: not offered by the host within {offer_wait_s} s (its saver may not play on that PC)')
                    raise FetchError(f'{name}: refused by the host ({reason})')
                if len(f) != 3 or f[0] != 'OK' or not f[1].isdigit() or not HEX64.fullmatch(f[2]):
                    raise FetchError(f'{name}: bad answer {head[:80]!r}')
                size, digest = int(f[1]), f[2]
                if expect_size is not None and size != expect_size:
                    raise FetchError(f'{name}: the host offers {size} bytes, not the expected {expect_size}')
                if expect_sha and digest != expect_sha:
                    raise FetchError(f'{name}: the host offers SHA-256 {digest[:16]}.., not the announced {expect_sha[:16]}..')
                if offset > size:
                    part.unlink()
                    continue
                with open(part, 'ab') as out:
                    got = offset
                    while got < size:
                        conn.settimeout(budget())
                        data = conn.recv(min(CHUNK, size - got))
                        _remaining(deadline)
                        if not data:
                            break
                        out.write(data)
                        _remaining(deadline)
                        got += len(data)
                        if progress:
                            progress(name, got, size)
                            _remaining(deadline)
                if got < size:
                    last = FetchError(f'{name}: connection lost at {got} of {size} bytes')
                    continue
            if sha256_file(part, deadline=deadline) != digest:
                part.unlink()
                last = FetchError(f'{name}: the downloaded bytes do not match SHA-256 {digest[:16]}..')
                continue
            _remaining(deadline)
            part.replace(dest)
            _remaining(deadline)
            return digest
        except FetchError:
            raise
        except (OSError, ValueError) as error:
            _remaining(deadline)
            last = FetchError(f'{name}: {error}')
    raise last or FetchError(f'{name}: no attempt left')
