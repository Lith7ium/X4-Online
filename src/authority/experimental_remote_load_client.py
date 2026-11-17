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
from .client_save_staging import copy_offered_save
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
    Optional keepalive requires a matching enabled server. Its interval must be
    chosen below the server idle timeout with room for network and scheduling
    delays. While awaiting X4 events the owner must call poll() often enough;
    there is no background thread. DNS and filesystem calls may still block.
    """
    def __init__(self, conn, *, enabled=False, file_host, file_port, file_token,
                 file_slot, deadline, io_timeout=30, keepalive_interval=None):
        if (enabled is not True or type(conn) is not socket.socket or conn.family != socket.AF_INET or
                conn.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM or
                conn.proto not in (0, socket.IPPROTO_TCP) or type(file_host) is not str or
                not file_host or len(file_host) > 253 or type(file_port) is not int or not 1 <= file_port <= 65535 or
                type(file_token) is not str or not re.fullmatch(r'[0-9a-f]{32}', file_token) or
                type(file_slot) is not int or not 1 <= file_slot <= 8 or
                type(deadline) not in (int,float) or not math.isfinite(deadline) or deadline <= time.monotonic() or
                type(io_timeout) not in (int,float) or not math.isfinite(io_timeout) or not 0 < io_timeout <= 300 or
                (keepalive_interval is not None and (type(keepalive_interval) not in (int,float) or
                 not math.isfinite(keepalive_interval) or not 0 < keepalive_interval <= 300))):
            raise ValueError('invalid enabled client, endpoint or deadline')
        conn.getpeername()
        conn.setblocking(False)
        self._conn = conn; self._endpoint = (file_host,file_port,file_token,file_slot)
        self._deadline = float(deadline); self._io_timeout = float(io_timeout)
        self._thread = threading.get_ident(); self._state = 'new'; self._busy = False
        self._bound = self._load = None
        self._keepalive_interval = keepalive_interval
        self._next_keepalive = None
        self._keepalive_sequence = 1

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

    def _wait(self, *, write=False, offer_response=False):
        duration = self._remaining() if offer_response else min(self._remaining(), self._io_timeout)
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

    def _read_frame(self, *, offer_response=False):
        # Never consume a subsequent participant command from the same stream.
        data = bytearray()
        while len(data) <= MAX_MESSAGE:
            self._wait(offer_response=offer_response)
            try: chunk = self._conn.recv(1)
            except BlockingIOError: continue
            if not chunk: raise ConnectionError('control connection closed')
            if chunk == b'\n': return bytes(data)
            data.extend(chunk)
        raise ValueError('control frame exceeds limit')

    def _pump(self):
        """Pump only on the owner thread, with no other frame in flight."""
        self._remaining()
        readable, _, exceptional = select.select([self._conn], [], [self._conn], 0)
        if readable or exceptional:
            raise ConnectionError('unexpected input during load')
        if time.monotonic() < self._next_keepalive:
            return
        started = time.monotonic()
        seq = self._keepalive_sequence
        request = {'version': 1, 'kind': 'keepalive',
                   'attempt_id': self._bound.offer.attempt_id, 'sequence': seq}
        self._send(json.dumps(request, separators=(',', ':'), sort_keys=True).encode('ascii') + b'\n')
        try:
            response = json.loads(self._read_frame().decode('utf-8'), object_pairs_hook=_pairs,
                                  parse_constant=_reject_constant)
        except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError('invalid keepalive response') from error
        if (type(response) is not dict or set(response) != {'version', 'kind', 'attempt_id', 'sequence'} or
                type(response['version']) is not int or response['version'] != 1 or response['kind'] != 'alive' or
                response['attempt_id'] != self._bound.offer.attempt_id or
                type(response['sequence']) is not int or response['sequence'] != seq):
            raise ValueError('keepalive response differs from current attempt')
        self._keepalive_sequence += 1
        self._next_keepalive = started + self._keepalive_interval

    def poll(self):
        """Maintain an enabled offer while the owner waits for local X4 events.

        This synchronously waits for a keepalive response. Each socket wait is
        capped by io_timeout; a fragmented response can take longer in total,
        but cannot extend the absolute load deadline.
        """
        with self._operation(self._state):
            if self._keepalive_interval is None or self._state not in (
                    'offered', 'downloaded', 'staged', 'requested', 'loaded', 'paused'):
                raise RuntimeError('no enabled active load to pump')
            self._pump()

    def request_offer(self):
        """Wait for a baseline within the existing overall load deadline.

        A not_ready response can occur while the server pauses and saves for
        this join. Retry only that exact protocol response, without overlapping
        requests or extending the caller's deadline. Other responses still fail
        closed. The offer response may take until the overall deadline because
        server pause/save is synchronous; EOF and socket errors remain visible.
        Other socket waits retain io_timeout.
        """
        with self._operation('new'):
            while True:
                self._send(offer_request())
                raw = self._read_frame(offer_response=True)
                try:
                    reply = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                                       parse_constant=_reject_constant)
                except (UnicodeError, json.JSONDecodeError, RecursionError):
                    reply = None
                if (type(reply) is dict and set(reply) == {'version', 'kind'} and
                        type(reply['version']) is int and reply['version'] == 1 and
                        reply['kind'] == 'not_ready'):
                    # No pipelining: unexpected data or EOF before the next
                    # request is a protocol failure, not another response.
                    delay = min(0.1, self._remaining())
                    readable, _, exceptional = select.select([self._conn], [], [self._conn], delay)
                    self._remaining()
                    if readable or exceptional:
                        raise ConnectionError('unexpected input between offer requests')
                    continue
                self._bound = decode_bound_offer(raw)
                self._load = ExperimentalClientLoad(enabled=True,offer=self._bound.offer,expected_marker=self._bound.marker)
                if self._keepalive_interval is not None:
                    self._next_keepalive = time.monotonic() + self._keepalive_interval
                self._state = 'offered'
                return self._bound

    def download(self, new_directory):
        """Download to a new exclusively owned directory; no retry or load."""
        with self._operation('offered'):
            offer = self._bound.offer
            save = SaveOffer(offer.name, offer.sha256, offer.size, offer.checkpoint_id)
            host, port, token, slot = self._endpoint
            options = {}
            if self._keepalive_interval is not None:
                options = {'pump': self._pump, 'pump_interval': min(.25, self._keepalive_interval / 2)}
            path = receive(host,port,token,slot,save,Path(new_directory),retries=0,
                           timeout=min(self._io_timeout,self._remaining()),deadline=self._deadline, **options)
            self._state = 'downloaded'
            return path

    def verify_staged(self, path):
        """Check a caller-staged copy before its X4 load is requested."""
        with self._operation('downloaded'):
            self._load.verify_staged(path, pump=self._pump if self._keepalive_interval is not None else None)
            self._state = 'staged'

    def copy_to_new_slot(self, source, target):
        """Copy to an absent X4 slot and verify it before local load.

        The caller exclusively controls both directories and fences X4's save
        scan until the copy completes. Failure can leave a partial or complete
        file at target for the caller to inspect; no existing slot is replaced.
        After failure the caller must keep X4 from scanning the target until any
        incomplete file has been handled under its control. This does not start
        X4 or establish that it loaded the staged bytes.
        """
        with self._operation('downloaded'):
            pump = self._pump if self._keepalive_interval is not None else self._remaining
            staged = copy_offered_save(source, target, self._bound.offer, pump=pump)
            self._load.verify_staged(staged, pump=pump)
            self._state = 'staged'
            return staged

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
            payload = encode_load_claim(self._load.make_claim(attempt, pump=self._pump if self._keepalive_interval is not None else None))
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
