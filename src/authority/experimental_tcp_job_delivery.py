"""Opt-in serialized NPC event exchange on admitted experimental TCP sockets.

No listener, X4 adapter, authentication or recovery is provided. The caller
must exclusively pump the existing host and its clients, supply a verified event
from the held source queue and wire each receipt to its delivery gate. This
bounded synchronous experiment blocks the host pump while it runs.
"""
import copy
import hashlib
import json
import math
import re
import secrets
import time

from .experimental_local_host import ExperimentalLocalHost
from .experimental_tcp_participants import ExperimentalTCPParticipants
from .load_messages import MAX_INTEGER, MAX_MESSAGE

_TOKEN = re.compile(r'[0-9a-f]{32}\Z')
_NAME = re.compile(r'[A-Za-z0-9_]{1,128}\Z')
_EVENT = {'epoch', 'generation', 'sequence', 'index', 'descriptor'}
_DESC = {'macro', 'faction', 'sector_macro', 'x', 'y', 'z'}


def job_event(value):
    """Validate and copy a Lua delivery-gate event; no actor handles allowed."""
    if type(value) is not dict or set(value) != _EVENT:
        raise ValueError('invalid job event')
    if any(type(value[k]) is not str or not _TOKEN.fullmatch(value[k]) for k in ('epoch', 'generation')):
        raise ValueError('invalid job lineage')
    if any(type(value[k]) is not int or not 1 <= value[k] <= MAX_INTEGER for k in ('sequence', 'index')):
        raise ValueError('invalid job identity')
    d = value['descriptor']
    if type(d) is not dict or set(d) != _DESC:
        raise ValueError('invalid descriptor')
    if any(type(d[k]) is not str or not _NAME.fullmatch(d[k]) for k in ('macro', 'faction', 'sector_macro')):
        raise ValueError('invalid descriptor name')
    for k in ('x', 'y', 'z'):
        n=d[k]
        if type(n) not in (int, float):raise ValueError('invalid descriptor coordinate')
        try: valid=math.isfinite(n)
        except OverflowError: valid=False
        if not valid:raise ValueError('invalid descriptor coordinate')
    return copy.deepcopy(value)


def job_digest(event):
    encoded=json.dumps(job_event(event),sort_keys=True,separators=(',', ':'),allow_nan=False).encode('ascii')
    return hashlib.sha256(encoded).hexdigest()


class ExperimentalTCPJobDelivery:
    """One event to the complete stable admitted set, one owned socket at a time.

    `membership()` returns stable `{id, incarnation}` pairs for the gate. The
    callback is invoked with that actual connection's pair and an event copy
    only after its exact receipt. Caller owns source/gate fencing on any fault;
    previously accepted client effects and source actions cannot be rolled back.
    """
    def __init__(self, host, *, enabled=False, timeout=30):
        if (enabled is not True or type(host) is not ExperimentalLocalHost or
                type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300):
            raise ValueError('enabled host and bounded timeout required')
        host._check()
        if host._control._job_delivery_owner is not None:
            raise ValueError('a delivery owner is already bound to these sockets')
        self._host=host;self._timeout=float(timeout);self._incarnations={}
        self._failed=False;self._last=None;self._queued=None;self._active=False
        host._control._job_delivery_owner=self

    def _peers(self):
        host=self._host;world=host._world.session
        if (world.state!='running' or world.pending is not None or not world.ready_players or
                len(world.ready_players)!=len(world.players)):
            raise RuntimeError('running fully admitted session required')
        handles=tuple(h for h,_ in world.ready_players)
        peers={}
        for conn,peer in host._control._peers.items():
            handle=peer['handle']
            if handle in handles:
                if handle in peers or peer['stage']!='admitted' or peer['in'] or peer['out']:
                    raise RuntimeError('admitted socket unavailable')
                peers[handle]=(conn,peer)
        if set(peers)!=set(handles) or len(handles)>16:
            raise RuntimeError('admitted socket set differs')
        self._incarnations={h:value for h,value in self._incarnations.items() if h in handles}
        for h in handles:
            if h not in self._incarnations:
                self._incarnations[h]=secrets.token_hex(16)
        return handles,peers

    def membership(self):
        if self._active:
            self._host._control._owner()
            if self._host._failed or not self._host._service.thread.is_alive():
                raise RuntimeError('host unavailable')
        else:self._host._check()
        if self._failed:raise RuntimeError('delivery faulted')
        handles,_=self._peers()
        return tuple({'id':'peer_'+str(h),'incarnation':self._incarnations[h]} for h in handles)

    def enqueue(self, peer, raw_event):
        """Gate send callback: accept one bounded local queue item, no I/O.

        Complete gate.begin before calling flush, so receipts never re-enter
        the gate while it is dispatching. A failed gate must be fenced by the
        owner; accepted queueing is not a network or client receipt.
        """
        try:
            members=self.membership();event=job_event(raw_event)
            if type(peer) is not dict or peer not in members:
                raise ValueError('foreign gate peer')
            if self._queued is None:
                self._queued={'event':event,'members':members,'seen':set()}
            queued=self._queued
            if queued['event']!=event or queued['members']!=members or peer['id'] in queued['seen']:
                raise ValueError('conflicting queued gate send')
            queued['seen'].add(peer['id'])
            return True
        except BaseException:
            self._failed=True;self._host._failed=True
            raise

    def flush(self, on_ack):
        """Exchange all queued sends after gate.begin has returned."""
        queued=self._queued
        if queued is None or queued['seen']!={p['id'] for p in queued['members']}:
            raise ValueError('incomplete gate dispatch')
        try:
            result=self.deliver(queued['event'],queued['members'],on_ack)
            self._queued=None
            return result
        except BaseException:
            self._failed=True;self._host._failed=True
            raise

    def deliver(self, raw_event, expected_members, on_ack):
        host=self._host;host._check()
        if self._failed or not callable(on_ack):raise RuntimeError('delivery unavailable')
        event=job_event(raw_event)
        if (self._last is not None and (event['epoch'],event['generation'])!=self._last[:2] or
                self._last is not None and event['sequence']!=self._last[2]+1):
            raise ValueError('stale or foreign event sequence')
        handles,peers=self._peers()
        membership=tuple({'id':'peer_'+str(h),'incarnation':self._incarnations[h]} for h in handles)
        if type(expected_members) not in (tuple,list) or list(expected_members)!=list(membership):
            raise ValueError('membership differs from gate')
        host._control._reader_free()
        lease=object();host._control._reader_lease=lease
        self._host._busy=True;self._active=True
        try:
            deadline=time.monotonic()+self._timeout
            ExperimentalTCPParticipants._quiet(self,peers,deadline)
            for h in handles:
                peer_id={'id':'peer_'+str(h),'incarnation':self._incarnations[h]}
                request={'version':1,'kind':'job_delivery','connection_handle':h,
                         'request_id':event['sequence'], 'session_epoch':host._world.session.world_epoch,
                         'incarnation':peer_id['incarnation'],'event':event}
                expected={k:request[k] for k in ('version','connection_handle','request_id','session_epoch','incarnation')}
                expected.update(kind='job_receipt',status='applied',event_sha256=job_digest(event))
                data=json.dumps(request,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()+b'\n'
                if len(data)>MAX_MESSAGE+1:raise ValueError('job frame too large')
                conn,peer=peers[h]
                others=[value[0] for k,value in peers.items() if k!=h]
                ExperimentalTCPParticipants._exchange(self,conn,peer,others,data,expected,deadline)
                if time.monotonic()>=deadline:raise TimeoutError('delivery callback deadline exceeded')
                if on_ack(dict(peer_id),copy.deepcopy(event)) is not True:
                    raise RuntimeError('delivery gate rejected receipt')
                if time.monotonic()>=deadline:raise TimeoutError('delivery callback deadline exceeded')
                if self._failed or host._failed:
                    raise RuntimeError('delivery changed during receipt callback')
                current,current_peers=self._peers()
                if current!=handles or any(current_peers[k]!=peers[k] for k in handles):
                    raise RuntimeError('admitted membership changed')
                ExperimentalTCPParticipants._quiet(self,peers,deadline)
            self._last=(event['epoch'],event['generation'],event['sequence'])
            return True
        except BaseException:
            self._failed=True;host._failed=True
            raise
        finally:
            changed=host._control._reader_lease is not lease
            if not changed:host._control._reader_lease=None
            else:self._failed=True;host._failed=True
            self._active=False;host._busy=False
            if changed:raise RuntimeError('exclusive socket lease changed during delivery')
