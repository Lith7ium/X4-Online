"""Opt-in local-only, read-only UDP exchange for one snapshot fixture.

The caller drives ``poll``; no thread or game hooks are installed. Numeric IPv4
loopback and independent 128-bit hex leases must be provisioned out of band for
this process lifetime. This diagnostic does not establish an identity
mapping, change the game, or authenticate traffic outside this host.

ASCII datagrams (no newline; at most 512 bytes):
  either -> adapter: FIX1|HELLO|<SOURCE or GUEST>|<role lease>|<fixture>
  adapter -> either: FIX1|READY|<SOURCE or GUEST>|<fixture>
  source -> adapter: FIX1|PUT|<source lease>|<fixture>|<seq>|<x>|<y>|<z>
  guest  -> adapter: FIX1|GET|<guest lease>|<fixture>|<request seq>
  adapter -> guest:  FIX1|POS|<fixture>|<request seq>|<source seq>|<x>|<y>|<z>

Sequence numbers are decimal integers in 1..2**53-1, strictly increasing per
role for the adapter lifetime. Coordinates are finite decimal numbers; the frame
is a pre-agreed fixture property and is not encoded. Invalid, unexpected, stale,
or oversized datagrams get no reply. GET gets no reply until a fresh PUT exists.
The returned source sequence lets a guest detect duplicate/reordered replies.
HELLO registers an as-yet-unregistered role to its observed source port. A
repeat HELLO from the same endpoint with the same lease re-sends READY; changing
endpoints requires a new adapter and new leases. Roles use distinct endpoints.
"""

import math
import re
import socket
import time

MAX_DATAGRAM = 512
MAX_SEQUENCE = (1 << 53) - 1  # exactly representable by X4's Lua number
_FIXTURE = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
_LEASE = re.compile(r"[0-9a-f]{32}\Z")
_SEQUENCE = re.compile(r"[1-9][0-9]{0,15}\Z")
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


def _sequence(value):
    if not _SEQUENCE.fullmatch(value):
        raise ValueError('invalid sequence')
    result = int(value)
    if result > MAX_SEQUENCE:
        raise ValueError('sequence exceeds exact Lua range')
    return result


def _coordinate(value):
    if not _DECIMAL.fullmatch(value):
        raise ValueError('invalid coordinate')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('coordinate must be finite')
    return result


class FixtureUDP:
    """Read-only exchange for exactly one source, guest and snapshot fixture."""

    def __init__(self, *, fixture, source_lease, guest_lease,
                 max_age_seconds, bind=('127.0.0.1', 0)):
        if not isinstance(fixture, str) or not _FIXTURE.fullmatch(fixture):
            raise ValueError('invalid registered snapshot fixture')
        self.source = self.guest = None
        if (not isinstance(source_lease, str) or not _LEASE.fullmatch(source_lease)
                or not isinstance(guest_lease, str) or not _LEASE.fullmatch(guest_lease)
                or source_lease == guest_lease):
            raise ValueError('roles require distinct 32-character lowercase hex leases')
        if (type(max_age_seconds) not in (int, float) or not math.isfinite(max_age_seconds)
                or not 0 < max_age_seconds <= 60):
            raise ValueError('max_age_seconds must be finite and in (0, 60]')
        if (not isinstance(bind, tuple) or len(bind) != 2 or bind[0] != '127.0.0.1'
                or type(bind[1]) is not int or not 0 <= bind[1] <= 65535):
            raise ValueError('diagnostic must bind to IPv4 loopback')
        self.fixture, self.source_lease, self.guest_lease = fixture, source_lease, guest_lease
        self.max_age = max_age_seconds
        self.source_seq = self.guest_seq = 0
        self.latest = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(bind)
            self.sock.setblocking(False)
        except BaseException:
            self.sock.close()
            raise

    @property
    def address(self):
        return self.sock.getsockname()

    def close(self):
        self.sock.close()

    def poll(self, max_packets=32):
        """Process at most max_packets queued datagrams; return number consumed."""
        if type(max_packets) is not int or not 1 <= max_packets <= 64:
            raise ValueError('max_packets must be an integer in 1..64')
        processed = 0
        while processed < max_packets:
            try:
                raw, sender = self.sock.recvfrom(MAX_DATAGRAM + 1)
            except BlockingIOError:
                break
            processed += 1
            if len(raw) > MAX_DATAGRAM or sender[0] != '127.0.0.1':
                continue
            try:
                parts = raw.decode('ascii').split('|')
                if len(parts) == 5 and parts[0:2] == ['FIX1', 'HELLO'] and parts[4] == self.fixture:
                    role, lease = parts[2:4]
                    if (role == 'SOURCE' and lease == self.source_lease and
                            (self.source is None or self.source == sender) and sender != self.guest):
                        self.source = sender
                    elif (role == 'GUEST' and lease == self.guest_lease and
                          (self.guest is None or self.guest == sender) and sender != self.source):
                        self.guest = sender
                    else:
                        continue
                    self.sock.sendto(f'FIX1|READY|{role}|{self.fixture}'.encode('ascii'), sender)
                elif (sender == self.source and len(parts) == 8 and parts[:3] ==
                        ['FIX1', 'PUT', self.source_lease] and parts[3] == self.fixture):
                    seq = _sequence(parts[4])
                    coordinates = tuple(_coordinate(v) for v in parts[5:8])
                    if seq > self.source_seq:
                        self.source_seq = seq
                        self.latest = (time.monotonic(), coordinates)
                elif (sender == self.guest and len(parts) == 5 and parts[:3] ==
                      ['FIX1', 'GET', self.guest_lease] and parts[3] == self.fixture):
                    request = _sequence(parts[4])
                    if request <= self.guest_seq:
                        continue
                    self.guest_seq = request
                    if self.latest is None or time.monotonic() - self.latest[0] > self.max_age:
                        continue
                    coordinates = '|'.join(repr(v) for v in self.latest[1])
                    reply = f'FIX1|POS|{self.fixture}|{request}|{self.source_seq}|{coordinates}'
                    self.sock.sendto(reply.encode('ascii'), self.guest)
            except (UnicodeError, ValueError, OverflowError):
                continue
        return processed
