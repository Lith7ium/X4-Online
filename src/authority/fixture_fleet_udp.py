"""Loopback-only read-only fleet experiment; neither X4 state nor Internet service.

Twelve out-of-band identities and their coordinate frames are fixed for the
lifetime of the process. All source and guest leases are distinct and ephemeral.
See docs/AUTHORITY-FLEET-DIAGNOSTIC.md for the wire format and its limitations.
"""
import math
import re
import socket
import time

from .fixture_udp import MAX_DATAGRAM, _FIXTURE, _LEASE, _coordinate, _sequence

_ROLE = re.compile(r'GUEST[1-8]\Z')


class FixtureFleetUDP:
    """One source and 1..8 guests; each fixture has independent sequences."""

    def __init__(self, *, fixtures, source_lease, guests, max_age_seconds, bind=('127.0.0.1', 0)):
        if (not isinstance(fixtures, dict) or len(fixtures) != 12 or
            any(not isinstance(k, str) or not _FIXTURE.fullmatch(k) or
                not isinstance(v, str) or not _FIXTURE.fullmatch(v) for k, v in fixtures.items())):
            raise ValueError('exactly 12 explicit fixture/frame pairs are required')
        if (not isinstance(guests, dict) or not 1 <= len(guests) <= 8 or
            any(not isinstance(k, str) or not _ROLE.fullmatch(k) for k in guests)):
            raise ValueError('one to eight named guests required')
        leases = [source_lease, *guests.values()]
        if any(not isinstance(v, str) or not _LEASE.fullmatch(v) for v in leases) or len(set(leases)) != len(leases):
            raise ValueError('distinct 128-bit lowercase hexadecimal leases required')
        if (type(max_age_seconds) not in (int, float) or not math.isfinite(max_age_seconds) or
            not 0 < max_age_seconds <= 60):
            raise ValueError('invalid max age')
        if (not isinstance(bind, tuple) or len(bind) != 2 or bind[0] != '127.0.0.1' or
            type(bind[1]) is not int or not 0 <= bind[1] <= 65535):
            raise ValueError('diagnostic requires IPv4 loopback')
        self.fixtures = dict(fixtures)
        self.leases = {'SOURCE': source_lease, **guests}
        self.endpoints = {}
        self.source_seq = {fixture: 0 for fixture in fixtures}
        self.guest_seq = {guest: {fixture: 0 for fixture in fixtures} for guest in guests}
        self.latest = {}
        self.max_age = max_age_seconds
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

    def poll(self, max_packets=64):
        if type(max_packets) is not int or not 1 <= max_packets <= 64:
            raise ValueError('max_packets must be in 1..64')
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
                p = raw.decode('ascii').split('|')
                if len(p) == 4 and p[:2] == ['FLEET1', 'HELLO']:
                    role, lease = p[2:]
                    if (role not in self.leases or self.leases[role] != lease or
                        (role in self.endpoints and self.endpoints[role] != sender) or
                        any(other != role and addr == sender for other, addr in self.endpoints.items())):
                        continue
                    self.endpoints[role] = sender
                    self.sock.sendto(f'FLEET1|READY|{role}'.encode('ascii'), sender)
                elif (len(p) == 9 and p[:2] == ['FLEET1', 'PUT'] and
                      self.endpoints.get('SOURCE') == sender and p[2] == self.leases['SOURCE']):
                    fixture, frame = p[3:5]
                    if self.fixtures.get(fixture) != frame:
                        continue
                    seq = _sequence(p[5])
                    coordinates = tuple(_coordinate(value) for value in p[6:9])
                    if seq > self.source_seq[fixture]:
                        self.source_seq[fixture] = seq
                        self.latest[fixture] = (time.monotonic(), coordinates)
                elif len(p) == 6 and p[:2] == ['FLEET1', 'GET']:
                    lease, fixture, frame, request = p[2:]
                    role = next((name for name, endpoint in self.endpoints.items()
                                 if name != 'SOURCE' and endpoint == sender and self.leases[name] == lease), None)
                    if role is None or self.fixtures.get(fixture) != frame:
                        continue
                    seq = _sequence(request)
                    if seq <= self.guest_seq[role][fixture]:
                        continue
                    self.guest_seq[role][fixture] = seq
                    latest = self.latest.get(fixture)
                    if latest is None or time.monotonic() - latest[0] > self.max_age:
                        continue
                    coords = '|'.join(repr(v) for v in latest[1])
                    reply = f'FLEET1|POS|{fixture}|{frame}|{seq}|{self.source_seq[fixture]}|{coords}'
                    self.sock.sendto(reply.encode('ascii'), sender)
            except (UnicodeError, ValueError, OverflowError):
                continue
        return processed
