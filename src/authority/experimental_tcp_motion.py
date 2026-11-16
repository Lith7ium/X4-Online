"""Opt-in serial motion messages on the existing admitted TCP delivery owner.

The owner must bind each epoch/generation/index to a real source lifetime before
calling track(). A receipt confirms the participant callback only: no X4 write,
frame equivalence, native velocity, lifecycle detection or recovery is implied.
"""
import copy
import hashlib
import json
import math
import re
import time

from .experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from .experimental_tcp_participants import ExperimentalTCPParticipants
from .load_messages import MAX_MESSAGE

_TOKEN = re.compile(r'[0-9a-f]{32}\Z')
_SECTOR = re.compile(r'[A-Za-z0-9_]{1,128}\Z')
_MAX = 9007199254740991
_COMMON = {'version', 'epoch', 'generation', 'index', 'sequence'}
_SNAPSHOT = _COMMON | {'sector_macro', 'source_time', 'x', 'y', 'z', 'velocity'}


def motion_value(value, *, despawn=False):
    """Validate exact portable fields and return a detached copy."""
    if type(despawn) is not bool or type(value) is not dict or set(value) != (_COMMON if despawn else _SNAPSHOT):
        raise ValueError('invalid motion fields')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('invalid motion version')
    if any(type(value[k]) is not str or not _TOKEN.fullmatch(value[k]) for k in ('epoch', 'generation')):
        raise ValueError('invalid motion lineage')
    if any(type(value[k]) is not int or not 1 <= value[k] <= _MAX for k in ('index', 'sequence')):
        raise ValueError('invalid motion identity')
    def number(n, lo, hi):
        if type(n) not in (int, float): return False
        try: return math.isfinite(n) and lo <= n <= hi
        except OverflowError: return False
    if not despawn:
        if type(value['sector_macro']) is not str or not _SECTOR.fullmatch(value['sector_macro']):
            raise ValueError('invalid motion frame')
        if not number(value['source_time'], 0, 1e12) or any(not number(value[k], -1e7, 1e7) for k in ('x','y','z')):
            raise ValueError('invalid motion sample')
        vel=value['velocity']
        if vel is not None and (type(vel) is not dict or set(vel)!={'x','y','z'} or
                any(not number(vel[k], -5000, 5000) for k in ('x','y','z'))):
            raise ValueError('invalid motion rate')
    return copy.deepcopy(value)


def motion_digest(value, *, despawn=False):
    raw=json.dumps(motion_value(value, despawn=despawn),sort_keys=True,separators=(',', ':'),allow_nan=False).encode('ascii')
    return hashlib.sha256(raw).hexdigest()


class ExperimentalTCPMotion:
    """Share the job owner's socket lease; callbacks own real game binding."""
    def __init__(self, delivery, *, enabled=False, min_interval=1/60, max_tracks=100000, allow_apply=False):
        if (enabled is not True or type(delivery) is not ExperimentalTCPJobDelivery or
            type(allow_apply) is not bool or type(min_interval) not in (int,float) or not math.isfinite(min_interval) or not 1/240 <= min_interval <= 10 or
            type(max_tracks) is not int or not 1 <= max_tracks <= 100000):
            raise ValueError('invalid enabled motion owner')
        delivery._host._check()
        if getattr(delivery, '_motion_owner', None) is not None:raise ValueError('motion owner already bound')
        delivery._motion_owner=self;self._delivery=delivery;self._tracks={};self._current={};self._source_owner=None;self._source_lease=None
        self._min_interval=float(min_interval);self._max_tracks=max_tracks;self._failed=False
        self._allow_apply=allow_apply;self._apply_attempted=False;self._preflight=None

    def _reserved(self,owner):
        if self._source_owner is not None and (owner is None or owner is not self._source_lease):
            self._failed=True;self._delivery._failed=True;self._delivery._host._failed=True
            raise RuntimeError('motion delivery is reserved by its source bridge')

    def track(self, epoch, generation, index, *, _source=None):
        self._reserved(_source)
        self._delivery._host._check()
        if self._failed or self._delivery._failed:raise RuntimeError('motion owner unavailable')
        try:probe=motion_value({'version':1,'epoch':epoch,'generation':generation,'index':index,'sequence':1},despawn=True)
        except (TypeError,ValueError):
            self._failed=True;self._delivery._failed=True;self._delivery._host._failed=True
            raise
        key=(probe['epoch'],probe['generation'],probe['index'])
        if key in self._tracks or len(self._tracks)>=self._max_tracks:
            self._failed=True;self._delivery._failed=True;self._delivery._host._failed=True
            raise ValueError('duplicate or full motion registry')
        current=self._current.get((epoch,index))
        if current is not None and not self._tracks[current]['closed']:
            self._failed=True;self._delivery._failed=True;self._delivery._host._failed=True
            raise ValueError('previous lifetime is still active')
        self._tracks[key]={'sequence':0,'time':None,'sent':None,'frame':None,'closed':False,'peer_frames':{},'peer_samples':{}}
        self._current[(epoch,index)]=key

    def send(self, raw, *, despawn=False, guard=None, recipients=None, _source=None):
        self._preflight=None
        self._reserved(_source)
        d=self._delivery;host=d._host;host._check()
        if not host._control._motion_idle():
            raise RuntimeError('drain latest motion before synchronous exchange')
        if despawn and host._control._latest_motion is not None and not host._control._latest_motion.blocked:
            raise RuntimeError('explicit motion barrier required before despawn')
        if self._failed or d._failed:raise RuntimeError('motion owner unavailable')
        if guard is not None and not callable(guard):raise ValueError('invalid motion operation guard')
        try:value=motion_value(raw,despawn=despawn)
        except (TypeError,ValueError):
            self._failed=True;d._failed=True;host._failed=True
            raise
        key=(value['epoch'],value['generation'],value['index'])
        state=self._tracks.get(key);now=time.monotonic()
        if not state or state['closed'] or value['sequence']<=state['sequence'] or (despawn and state['sequence']==0):
            self._failed=True;d._failed=True;host._failed=True
            raise ValueError('unknown, stale or despawned motion')
        if not despawn:
            if state['time'] is not None and value['source_time']<=state['time']:
                self._failed=True;d._failed=True;host._failed=True
                raise ValueError('non-monotone source time')
            if state['frame'] is not None and value['sector_macro']!=state['frame'] and value['velocity'] is not None:
                self._failed=True;d._failed=True;host._failed=True
                raise ValueError('frame transition requires unknown velocity')
            if state['sent'] is not None and now-state['sent']<self._min_interval:
                raise ValueError('motion rate limited')
        try:
            members=d.membership();handles,peers=d._peers()
            if not members:raise RuntimeError('no admitted motion recipients')
            # Snapshot full membership and exact socket incarnations even when
            # the caller selects only some participants. All other sockets
            # remain fenced and must remain quiet throughout the exchange.
            incarnations=dict(d._incarnations)
            full={(m['id'],m['incarnation']) for m in members}
            if len(full)!=len(handles) or full!={('peer_'+str(h),incarnations[h]) for h in handles}:
                raise RuntimeError('motion membership changed')
            # Only peers that confirmed a snapshot know this lifetime. A
            # despawn must reach every such connected incarnation; sending it
            # to an uninformed peer is invalid on the participant as well.
            required=full.intersection(state['peer_samples']) if despawn else None
            if recipients is None:
                selected=(tuple(h for h in handles if ('peer_'+str(h),incarnations[h]) in required)
                          if despawn else handles)
            else:
                if type(recipients) not in (tuple,list) or (not recipients and not despawn):
                    raise ValueError('nonempty explicit motion recipients required')
                wanted=set()
                for peer in recipients:
                    if (type(peer) is not dict or set(peer)!={'id','incarnation'} or
                        type(peer['id']) is not str or type(peer['incarnation']) is not str):
                        raise ValueError('invalid motion recipient')
                    identity=(peer['id'],peer['incarnation'])
                    if identity in wanted or identity not in full:raise ValueError('duplicate or foreign motion recipient')
                    wanted.add(identity)
                if despawn and wanted != required:
                    raise ValueError('despawn requires every informed connected recipient')
                selected=tuple(h for h in handles if ('peer_'+str(h),incarnations[h]) in wanted)
            if not despawn:
                for h in selected:
                    peer=('peer_'+str(h),incarnations[h])
                    if peer in state['peer_frames'] and state['peer_frames'][peer]!=value['sector_macro']:
                        raise ValueError('recipient motion frame changed without resync')
            host._control._reader_free()
        except BaseException:
            self._failed=True;d._failed=True;host._failed=True
            raise
        lease=object();host._control._reader_lease=lease
        host._busy=True;d._active=True
        try:
            deadline=time.monotonic()+d._timeout
            def check_guard():
                if guard is not None and guard() is not True:raise RuntimeError('motion operation guard failed')
                if (time.monotonic()>=deadline or self._failed or d._failed or host._failed or
                    host._busy is not True or d._active is not True or host._control._reader_lease is not lease or
                    d._incarnations!=incarnations):
                    raise RuntimeError('motion operation state changed')
            check_guard()
            ExperimentalTCPParticipants._quiet(d,peers,deadline)
            for h in selected:
                check_guard()
                incarnation=incarnations[h]
                req={'version':1,'kind':'motion_despawn' if despawn else 'motion_snapshot',
                     'connection_handle':h,'session_epoch':host._world.session.world_epoch,
                     'incarnation':incarnation,'request_id':value['sequence'],'sample':value}
                expected={k:req[k] for k in ('version','connection_handle','session_epoch','incarnation','request_id')}
                expected.update(kind='motion_receipt',status='accepted',sample_sha256=motion_digest(value,despawn=despawn))
                data=json.dumps(req,sort_keys=True,separators=(',', ':'),allow_nan=False).encode('ascii')+b'\n'
                if len(data)>MAX_MESSAGE+1:raise ValueError('motion frame too large')
                conn,peer=peers[h];others=[p[0] for n,p in peers.items() if n!=h]
                ExperimentalTCPParticipants._exchange(d,conn,peer,others,data,expected,deadline,check=check_guard if guard else None)
                check_guard()
                current,current_peers=d._peers()
                if (current!=handles or any(current_peers[k]!=peers[k] for k in handles) or
                    d._incarnations!=incarnations):raise RuntimeError('motion membership changed')
                ExperimentalTCPParticipants._quiet(d,peers,deadline)
            check_guard()
            state['sequence']=value['sequence'];state['sent']=time.monotonic();state['closed']=despawn
            if not despawn:
                state['time']=value['source_time'];state['frame']=value['sector_macro']
                for h in selected:
                    peer=('peer_'+str(h),incarnations[h]);state['peer_frames'][peer]=value['sector_macro']
                    state['peer_samples'][peer]=(value['sequence'],motion_digest(value))
            return True
        except BaseException:
            self._failed=True;d._failed=True;host._failed=True
            raise
        finally:
            changed=host._control._reader_lease is not lease
            if not changed:host._control._reader_lease=None
            else:self._failed=True;d._failed=True;host._failed=True
            d._active=False;host._busy=False
            if changed:raise RuntimeError('motion socket lease changed')

    def enqueue_latest(self, raw, *, recipients=None, _source=None, _guard=None):
        """Queue a replaceable position for the existing control poll owner.

        Queueing is not receipt, delivery, X4 application, or interest discovery.
        A lifecycle caller must establish and drain control.motion_barrier().
        """
        self._reserved(_source)
        d=self._delivery;host=d._host;host._check();control=host._control
        if _guard is not None and not callable(_guard):raise ValueError('invalid latest motion guard')
        latest=control._latest_motion
        if latest is None or self._failed or d._failed or d._active or d._test_binding is not None:
            raise RuntimeError('latest motion unavailable')
        if latest.blocked or latest.world_blocked:
            raise RuntimeError('motion fenced by lifecycle barrier')
        value=motion_value(raw);key=(value['epoch'],value['generation'],value['index'])
        state=self._tracks.get(key)
        if not state or state['closed'] or value['sequence']<=state['sequence']:
            raise ValueError('unknown, closed or stale motion track')
        if state['time'] is not None and value['source_time']<=state['time']:
            raise ValueError('non-monotone source time')
        if state['frame'] is not None and value['sector_macro']!=state['frame'] and value['velocity'] is not None:
            raise ValueError('frame transition requires unknown velocity')
        handles,peers=d._peers();incarnations=dict(d._incarnations)
        if not handles: raise RuntimeError('no admitted motion recipients')
        full={('peer_'+str(h),incarnations[h]):h for h in handles}
        if recipients is None: selected=handles
        else:
            if type(recipients) not in (tuple,list) or not recipients:
                raise ValueError('nonempty recipients required')
            wanted=set()
            for peer in recipients:
                if type(peer) is not dict or set(peer)!={'id','incarnation'}:
                    raise ValueError('invalid motion recipient')
                identity=(peer['id'],peer['incarnation'])
                if identity not in full or identity in wanted: raise ValueError('foreign or duplicate motion recipient')
                wanted.add(identity)
            selected=tuple(h for h in handles if ('peer_'+str(h),incarnations[h]) in wanted)
        reserved=state.setdefault('latest_frames',{})
        for h in selected:
            identity=('peer_'+str(h),incarnations[h])
            frame=reserved.get(identity,state['peer_frames'].get(identity))
            if frame is not None and frame!=value['sector_macro']:
                raise ValueError('recipient motion frame changed without resync')
        entries=[];digest=motion_digest(value)
        for h in selected:
            identity=('peer_'+str(h),incarnations[h]);conn,peer=peers[h]
            request={'version':1,'kind':'motion_snapshot','connection_handle':h,
                     'session_epoch':host._world.session.world_epoch,'incarnation':incarnations[h],
                     'request_id':value['sequence'],'sample':value}
            expected={k:request[k] for k in ('version','connection_handle','session_epoch','incarnation','request_id')}
            expected.update(kind='motion_receipt',status='accepted',sample_sha256=digest)
            data=json.dumps(request,sort_keys=True,separators=(',', ':'),allow_nan=False).encode('ascii')+b'\n'
            if len(data)>MAX_MESSAGE+1: raise ValueError('motion frame too large')
            def accepted(identity=identity, h=h, conn=conn, peer=peer):
                if (control._peers.get(conn) is not peer or d._incarnations.get(h)!=identity[1] or
                        host._world.session.world_epoch!=request_epoch):
                    raise RuntimeError('motion receipt context changed')
                state['peer_frames'][identity]=value['sector_macro']
                state['peer_samples'][identity]=(value['sequence'],digest)
            def discarded(identity=identity, peer=peer):
                active=peer.get('motion_active')
                if identity not in state['peer_frames'] and not (
                        active is not None and active['key']==key and active['sent']>0):
                    reserved.pop(identity,None)
            request_epoch=request['session_epoch']
            entries.append((conn,peer,key,data,expected,accepted,discarded,_guard))
        survivors=latest.enqueue(entries)
        state['sequence']=value['sequence'];state['time']=value['source_time'];state['frame']=value['sector_macro']
        for h in selected:
            if peers[h][0] in survivors:reserved[('peer_'+str(h),incarnations[h])]=value['sector_macro']
        self._preflight=None
        return bool(survivors)

    def apply_once(self,raw,*,guard=None,_source=None):
        """Opt-in one-peer apply/readback after an exactly confirmed motion sample.

        This is a caller assertion; a failure after dispatch cannot undo a write.
        """
        self._reserved(_source);d=self._delivery;host=d._host;host._check()
        if not host._control._motion_idle(): raise RuntimeError('drain latest motion before apply')
        try:
            if not self._allow_apply or self._apply_attempted or self._failed or d._failed:
                raise RuntimeError('one-shot motion apply unavailable')
            if guard is not None and not callable(guard):raise ValueError('invalid operation guard')
            value=motion_value(raw);key=(value['epoch'],value['generation'],value['index'])
            state=self._tracks.get(key);members=d.membership();handles,peers=d._peers();incarnations=dict(d._incarnations)
            if len(members)!=1 or len(handles)!=1:raise RuntimeError('one admitted apply participant required')
            h=handles[0];peer=('peer_'+str(h),incarnations[h]);digest=motion_digest(value)
            if (not state or state['closed'] or state['peer_samples'].get(peer)!=(value['sequence'],digest) or
                self._preflight!=(key,peer,value['sequence'],digest) or
                members!=({'id':peer[0],'incarnation':peer[1]},)):
                raise ValueError('apply sample is not the confirmed participant sample')
            host._control._reader_free()
        except BaseException:
            self._failed=True;d._failed=True;host._failed=True;raise
        lease=object();host._control._reader_lease=lease;host._busy=True;d._active=True;self._apply_attempted=True
        try:
            deadline=time.monotonic()+d._timeout
            def check():
                if guard is not None and guard() is not True:raise RuntimeError('motion apply guard failed')
                if (time.monotonic()>=deadline or self._failed or d._failed or host._failed or host._busy is not True or
                    d._active is not True or host._control._reader_lease is not lease or d._incarnations!=incarnations):
                    raise RuntimeError('motion apply state changed')
            check();ExperimentalTCPParticipants._quiet(d,peers,deadline)
            req={'version':1,'kind':'motion_apply','connection_handle':h,'session_epoch':host._world.session.world_epoch,
                 'incarnation':incarnations[h],'request_id':value['sequence'],'sample':value}
            expected={k:req[k] for k in ('version','connection_handle','session_epoch','incarnation','request_id')}
            expected.update(kind='motion_applied_receipt',status='applied',sample_sha256=digest)
            data=json.dumps(req,sort_keys=True,separators=(',', ':'),allow_nan=False).encode('ascii')+b'\n'
            if len(data)>MAX_MESSAGE+1:raise ValueError('motion apply frame too large')
            conn,p=peers[h]
            ExperimentalTCPParticipants._exchange(d,conn,p,[],data,expected,deadline,check=check if guard else None)
            check();current,current_peers=d._peers()
            if current!=handles or current_peers[h]!=peers[h] or d._incarnations!=incarnations:
                raise RuntimeError('motion apply membership changed')
            ExperimentalTCPParticipants._quiet(d,peers,deadline);check();return True
        except BaseException:
            self._failed=True;d._failed=True;host._failed=True;raise
        finally:
            changed=host._control._reader_lease is not lease
            if not changed:host._control._reader_lease=None
            else:self._failed=True;d._failed=True;host._failed=True
            d._active=False;host._busy=False
            if changed:raise RuntimeError('motion apply reader lease changed')

    def preflight(self,raw,*,guard=None,_source=None):
        """Read-only, correlated preflight for the last confirmed peer sample."""
        self._reserved(_source);d=self._delivery;host=d._host;host._check();self._preflight=None
        if not host._control._motion_idle(): raise RuntimeError('drain latest motion before preflight')
        try:
            if not self._allow_apply or self._apply_attempted or self._failed or d._failed:
                raise RuntimeError('motion preflight unavailable')
            if guard is not None and not callable(guard):raise ValueError('invalid operation guard')
            value=motion_value(raw);key=(value['epoch'],value['generation'],value['index'])
            state=self._tracks.get(key);members=d.membership();handles,peers=d._peers();incarnations=dict(d._incarnations)
            if len(members)!=1 or len(handles)!=1:raise RuntimeError('one admitted preflight participant required')
            h=handles[0];peer=('peer_'+str(h),incarnations[h]);digest=motion_digest(value)
            if (not state or state['closed'] or state['peer_samples'].get(peer)!=(value['sequence'],digest) or
                members!=({'id':peer[0],'incarnation':peer[1]},)):
                raise ValueError('preflight sample is not the confirmed participant sample')
            host._control._reader_free()
        except BaseException:
            self._failed=True;d._failed=True;host._failed=True;raise
        lease=object();host._control._reader_lease=lease;host._busy=True;d._active=True
        try:
            deadline=time.monotonic()+d._timeout
            def check():
                if guard is not None and guard() is not True:raise RuntimeError('motion preflight guard failed')
                if (time.monotonic()>=deadline or self._failed or d._failed or host._failed or host._busy is not True or
                    d._active is not True or host._control._reader_lease is not lease or d._incarnations!=incarnations):
                    raise RuntimeError('motion preflight state changed')
            check();ExperimentalTCPParticipants._quiet(d,peers,deadline)
            req={'version':1,'kind':'motion_preflight','connection_handle':h,'session_epoch':host._world.session.world_epoch,
                 'incarnation':incarnations[h],'request_id':value['sequence'],'sample':value}
            expected={k:req[k] for k in ('version','connection_handle','session_epoch','incarnation','request_id')}
            expected.update(kind='motion_preflight_receipt',sample_sha256=digest)
            choices=tuple(dict(expected,status=status) for status in ('near','ready'))
            data=json.dumps(req,sort_keys=True,separators=(',', ':'),allow_nan=False).encode('ascii')+b'\n'
            if len(data)>MAX_MESSAGE+1:raise ValueError('motion preflight frame too large')
            conn,p=peers[h]
            answer=ExperimentalTCPParticipants._exchange(d,conn,p,[],data,choices,deadline,check=check if guard else None)
            check();current,current_peers=d._peers()
            if current!=handles or current_peers[h]!=peers[h] or d._incarnations!=incarnations:
                raise RuntimeError('motion preflight membership changed')
            ExperimentalTCPParticipants._quiet(d,peers,deadline);check()
            if answer['status']=='ready':self._preflight=(key,peer,value['sequence'],digest)
            return answer['status']
        except BaseException:
            self._failed=True;d._failed=True;host._failed=True;raise
        finally:
            changed=host._control._reader_lease is not lease
            if not changed:host._control._reader_lease=None
            else:self._failed=True;d._failed=True;host._failed=True
            d._active=False;host._busy=False
            if changed:raise RuntimeError('motion preflight reader lease changed')
