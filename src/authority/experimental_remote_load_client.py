"""One cooperative load attempt over caller-supplied connected TCP.

No listener, X4 integration, endpoint discovery, authentication or encryption
is supplied. The caller exclusively owns the socket, destination and local
game process; supplied load/marker/pause observations are trusted assertions.
"""
from contextlib import contextmanager
import json
import math
from pathlib import Path
import re
import select
import socket
import threading
import time

from .experimental_client_load import ExperimentalClientLoad
from .experimental_tcp_control import offer_request
from .load_messages import MAX_MESSAGE, _pairs, _reject_constant
from .save_transfer import SaveOffer, receive
from .trusted_load_messages import decode_bound_offer, encode_load_claim


class ExperimentalRemoteLoadClient:
    """Single-owner, single-attempt state machine.

    Once construction succeeds, failures in owner operations close TCP. A
    rejected constructor leaves its input socket with the caller; a call from
    another thread is rejected without changing the owner's socket or state.

    A caller supplies an already-connected IPv4 TCP stream, a file endpoint,
    and a monotonic absolute deadline. `download` uses the existing file fetcher:
    its socket operations are capped by the same absolute deadline. DNS,
    filesystem calls and callbacks cannot be interrupted; the deadline is
    checked after each returns. The caller must keep the download and staged paths
    exclusive, and establish that reported observations belong to the still-live
    X4 process. No native file consumption or peer authenticity is proven.
    """
    def __init__(self, conn, *, enabled=False, file_host, file_port, file_token,
                 file_slot, deadline, io_timeout=30):
        if (enabled is not True or type(conn) is not socket.socket or conn.family != socket.AF_INET or
                conn.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM or
                conn.proto not in (0, socket.IPPROTO_TCP) or type(file_host) is not str or
                not file_host or len(file_host) > 253 or type(file_port) is not int or not 1 <= file_port <= 65535 or
                type(file_token) is not str or not re.fullmatch(r'[0-9a-f]{32}', file_token) or
                type(file_slot) is not int or not 1 <= file_slot <= 8 or
                type(deadline) not in (int,float) or not math.isfinite(deadline) or deadline <= time.monotonic() or
                type(io_timeout) not in (int,float) or not math.isfinite(io_timeout) or not 0 < io_timeout <= 300):
            raise ValueError('invalid enabled client, endpoint or deadline')
        conn.getpeername()
        conn.setblocking(False)
        self._conn = conn; self._endpoint = (file_host,file_port,file_token,file_slot)
        self._deadline = float(deadline); self._io_timeout = float(io_timeout)
        self._thread = threading.get_ident(); self._state = 'new'; self._busy = False
        self._bound = self._load = None

    def _remaining(self):
        value = self._deadline-time.monotonic()
        if value <= 0: raise TimeoutError('load attempt deadline expired')
        return value

    def _fault(self):
        self._state = 'failed'
        if self._load is not None: self._load.close()
        if self._conn is not None:
            try: self._conn.close()
            except OSError: pass
            self._conn = None

    @contextmanager
    def _operation(self, expected):
        if threading.get_ident() != self._thread: raise RuntimeError('exclusive owner thread required')
        if self._busy or self._state != expected:
            self._fault(); raise RuntimeError('reentrant, stale or out-of-order load operation')
        self._busy = True
        try:
            self._remaining(); yield; self._remaining()
        except BaseException:
            self._fault(); raise
        finally: self._busy = False

    def _wait(self, *, write=False):
        duration = min(self._remaining(), self._io_timeout)
        read, writable, exceptional = select.select([] if write else [self._conn],
            [self._conn] if write else [], [self._conn], duration)
        self._remaining()
        if exceptional or not (writable if write else read): raise TimeoutError('control I/O failed or timed out')

    def _send(self, data):
        view = memoryview(data)
        while view:
            self._wait(write=True)
            try: sent = self._conn.send(view)
            except BlockingIOError: continue
            if sent <= 0: raise ConnectionError('control connection closed')
            view = view[sent:]

    def _read_frame(self):
        # Never consume a subsequent participant command from the same stream.
        data = bytearray()
        while len(data) <= MAX_MESSAGE:
            self._wait()
            try: chunk = self._conn.recv(1)
            except BlockingIOError: continue
            if not chunk: raise ConnectionError('control connection closed')
            if chunk == b'\n': return bytes(data)
            data.extend(chunk)
        raise ValueError('control frame exceeds limit')

    def request_offer(self):
        with self._operation('new'):
            self._send(offer_request())
            self._bound = decode_bound_offer(self._read_frame())
            self._load = ExperimentalClientLoad(enabled=True,offer=self._bound.offer,expected_marker=self._bound.marker)
            self._state = 'offered'
            return self._bound

    def download(self, new_directory):
        """Download to a new exclusively owned directory; no retry or load."""
        with self._operation('offered'):
            offer = self._bound.offer
            save = SaveOffer(offer.name, offer.sha256, offer.size, offer.checkpoint_id)
            host, port, token, slot = self._endpoint
            path = receive(host,port,token,slot,save,Path(new_directory),retries=0,
                           timeout=min(self._io_timeout,self._remaining()),deadline=self._deadline)
            self._state = 'downloaded'
            return path

    def verify_staged(self, path):
        """Check a caller-staged copy before its X4 load is requested."""
        with self._operation('downloaded'):
            self._load.verify_staged(path); self._state = 'staged'

    def load_requested(self, attempt):
        with self._operation('staged'):
            self._load.observe_load_requested(attempt); self._state = 'requested'

    def loaded_marker(self, attempt, marker):
        with self._operation('requested'):
            self._load.observe_loaded_marker(attempt,marker); self._state = 'loaded'

    def paused(self, attempt, paused):
        with self._operation('loaded'):
            self._load.observe_pause(attempt,paused); self._state = 'paused'

    def claim(self, attempt):
        with self._operation('paused'):
            # Refuse an already queued response, EOF, or exceptional socket.
            readable, _, exceptional = select.select([self._conn], [], [self._conn], 0)
            if readable or exceptional: raise ConnectionError('unexpected input before claim')
            payload = encode_load_claim(self._load.make_claim(attempt))
            self._send(payload+b'\n')
            try: ack = json.loads(self._read_frame().decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_reject_constant)
            except (UnicodeError,json.JSONDecodeError,RecursionError) as error: raise ValueError('invalid accepted frame') from error
            if (type(ack) is not dict or set(ack) != {'version','kind','attempt_id'} or
                    type(ack['version']) is not int or ack['version'] != 1 or ack['kind'] != 'accepted' or
                    ack['attempt_id'] != self._bound.offer.attempt_id):
                raise ValueError('accepted frame differs from current attempt')
            self._state = 'accepted'

    def take_connection(self):
        """Transfer exclusive socket ownership once after successful admission."""
        with self._operation('accepted'):
            conn = self._conn
        self._conn = None; self._state = 'transferred'
        return conn

    def close(self):
        if threading.get_ident() != self._thread or self._busy: raise RuntimeError('exclusive owner thread required')
        if self._conn is not None: self._conn.close(); self._conn = None
        if self._load is not None: self._load.close()
        self._state = 'closed'
