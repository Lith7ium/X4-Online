"""Per-peer latest-motion I/O for the experimental control poll owner.

This is not a transport, lifecycle replication, or an X4 source. One owner
thread must poll the control channel and explicitly fence lifecycle operations.
Only an unsent sample may be replaced; a started frame and its receipt remain
in flight until completion or the peer is disconnected.
"""
import json
import time

from .load_messages import MAX_MESSAGE, _pairs, _reject_constant


class LatestMotionPoll:
    def __init__(self, control, *, limit, timeout):
        self.control = control
        self.limit = limit
        self.timeout = timeout
        self.blocked = False
        self.world_blocked = False

    def busy(self):
        return any(p.get('motion_active') or p.get('motion_pending')
                   for p in self.control._peers.values())

    def enqueue(self, entries):
        if self.blocked or self.world_blocked:
            raise RuntimeError('motion is fenced for a lifecycle operation')
        # Preflight the complete set, so capacity failure sends to no peer.
        for conn, peer, key, data, expected, accepted, discarded in entries:
            if self.control._peers.get(conn) is not peer or peer['stage'] != 'admitted':
                raise RuntimeError('motion peer changed')
            pending = peer.setdefault('motion_pending', {})
            if key not in pending and len(pending) >= self.limit:
                raise BufferError('per-peer motion queue full')
        for conn, peer, key, data, expected, accepted, discarded in entries:
            peer['motion_pending'][key] = (data, expected, accepted, discarded)

    def barrier(self, *, world=False):
        if world: self.world_blocked = True
        else: self.blocked = True
        for peer in self.control._peers.values():
            active = peer.get('motion_active')
            if active is not None and active['sent'] == 0:
                peer['motion_active'] = None
                active['discarded']()
            pending = peer.get('motion_pending', {})
            for _, _, _, discarded in pending.values(): discarded()
            pending.clear()
        return not self.busy()

    def release(self, *, world=False):
        if self.busy(): raise RuntimeError('motion barrier has not drained')
        if world: self.world_blocked = False
        else: self.blocked = False

    def prepare(self, peer):
        if self.blocked or self.world_blocked or peer.get('motion_active') or peer['out']:
            return
        pending = peer.get('motion_pending', {})
        if pending:
            key = next(iter(pending))
            data, expected, accepted, discarded = pending.pop(key)
            peer['motion_active'] = {'key': key, 'data': data, 'sent': 0, 'input': b'',
                                     'expected': expected, 'accepted': accepted, 'discarded': discarded,
                                     'deadline': time.monotonic() + self.timeout}

    def send(self, conn, peer):
        active = peer['motion_active']
        try: count = conn.send(active['data'][active['sent']:])
        except BlockingIOError: return
        if count <= 0:
            self.control._drop(conn)
            return
        active['sent'] += count

    def receive(self, conn, peer, chunk):
        active = peer.get('motion_active')
        if active is None or active['sent'] != len(active['data']):
            self.control._drop(conn); return
        active['input'] += chunk
        if b'\n' not in active['input']:
            if len(active['input']) > MAX_MESSAGE: self.control._drop(conn)
            return
        raw, tail = active['input'].split(b'\n', 1)
        if tail or len(raw) > MAX_MESSAGE:
            self.control._drop(conn); return
        try:
            reply = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                               parse_constant=_reject_constant)
            expected = active['expected']
            if (type(reply) is not dict or set(reply) != set(expected) or
                    any(type(reply.get(k)) is not type(v) or reply[k] != v for k, v in expected.items())):
                raise ValueError('invalid motion receipt')
            active['accepted']()
        except (ValueError, UnicodeError, RecursionError):
            self.control._drop(conn); return
        peer['motion_active'] = None
