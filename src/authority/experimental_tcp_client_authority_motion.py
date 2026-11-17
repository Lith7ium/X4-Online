"""Opt-in server-initiated, read-only test-grant client motion pull.

One explicitly selected participant, or the legacy sole participant, shares the
existing exclusive control reader. Selection is fenced by its incarnation.
The grant is a caller assertion, not HA ownership or authentication; the
caller owns all X4 lifecycle, PID/UDP-inode validation and failure fencing.
"""
import copy
import json
import re
import time
from .experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from .experimental_tcp_participants import ExperimentalTCPParticipants
from .experimental_tcp_motion import motion_value, motion_digest
from .load_messages import MAX_MESSAGE

_TOKEN=re.compile(r'[0-9a-f]{32}\Z')
_MAX=9007199254740991


def grant_value(value):
    fields={'session_epoch','epoch','generation','index','sector_macro','token','incarnation'}
    if type(value) is not dict or set(value)!=fields:raise ValueError('invalid authority test grant')
    if any(type(value[k]) is not str or not _TOKEN.fullmatch(value[k]) for k in ('epoch','generation','token','incarnation')):
        raise ValueError('invalid authority grant token')
    if len({value[k] for k in ('epoch','generation','token','incarnation')})!=4:raise ValueError('authority grant tokens overlap')
    if type(value['session_epoch']) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value['session_epoch']):raise ValueError('invalid authority session epoch')
    motion_value({'version':1,'epoch':value['epoch'],'generation':value['generation'],'index':value['index'],
                  'sequence':1,'sector_macro':value['sector_macro'],'source_time':0,'x':0,'y':0,'z':0,'velocity':None})
    return copy.deepcopy(value)


class ExperimentalTCPClientAuthorityMotion:
    """One immutable test grant and one serialized, non-writing participant pull."""
    def __init__(self,delivery,*,enabled=False,grant,guard,connection_handle=None):
        if enabled is not True or type(delivery) is not ExperimentalTCPJobDelivery or not callable(guard):
            raise ValueError('enabled authority pull and guard required')
        if connection_handle is not None and (type(connection_handle) is not int or not 1<=connection_handle<=_MAX):
            raise ValueError('invalid authority participant handle')
        delivery._host._check()
        if getattr(delivery,'_client_authority_owner',None) is not None:raise ValueError('authority pull already owned')
        existing=getattr(delivery,'_client_authority_selected_owners',None)
        if existing is not None and (connection_handle is None or connection_handle in existing or len(existing)>=2):
            raise ValueError('authority participant already owned or capacity reached')
        checked_grant=grant_value(grant)
        if (checked_grant['incarnation'] in delivery._retired_authority_incarnations or
                checked_grant['token'] in delivery._retired_authority_tokens):
            raise ValueError('retired authority grant')
        if existing and any(owner._grant['incarnation']==checked_grant['incarnation'] or
                            owner._grant['token']==checked_grant['token'] or
                            owner._grant['index']==checked_grant['index'] for owner in existing.values()):
            raise ValueError('authority grant or ship reused across participants')
        self._grant=checked_grant;self._grant_wire=json.dumps(self._grant,sort_keys=True,separators=(',',':'));self._guard=guard;self._delivery=delivery
        self._retired_identity = (checked_grant['incarnation'], checked_grant['token'])
        self._connection_handle=connection_handle
        self._request=0;self._last_sequence=0;self._last_time=None;self._failed=False;self._busy=False;self._revoked=False
        if connection_handle is None:delivery._client_authority_owner=self
        else:
            if existing is None:existing={};delivery._client_authority_selected_owners=existing
            existing[connection_handle]=self
    def _guarded(self):
        probe=copy.deepcopy(self._grant);state=(self._request,self._last_sequence,self._last_time,self._connection_handle)
        if (json.dumps(self._grant,sort_keys=True,separators=(',',':'))!=self._grant_wire or self._guard(probe) is not True or
            json.dumps(probe,sort_keys=True,separators=(',',':'))!=self._grant_wire or
            json.dumps(self._grant,sort_keys=True,separators=(',',':'))!=self._grant_wire or
            state!=(self._request,self._last_sequence,self._last_time,self._connection_handle)):
            raise RuntimeError('authority grant guard changed')
    def pull(self):
        if self._revoked or self._delivery._authority_suspended:
            raise RuntimeError('authority grant is revoked or suspended')
        owners=getattr(self._delivery,'_client_authority_selected_owners',{})
        if self._busy or any(owner is not self and owner._busy for owner in owners.values()):
            self._failed=True;self._delivery._failed=True;self._delivery._host._failed=True
            raise RuntimeError('reentrant authority pull')
        self._busy=True
        try:return self._pull()
        finally:self._busy=False

    def revoke(self):
        """Retire a selected grant while its delivery is suspended and idle."""
        delivery = self._delivery
        delivery._host._check()
        delivery._host._control._reader_free()
        owners = getattr(delivery, '_client_authority_selected_owners', {})
        if (self._revoked or self._connection_handle is None or not delivery._authority_suspended or
                self._busy or delivery._active or delivery._test_bind_busy or
                owners.get(self._connection_handle) is not self):
            raise RuntimeError('authority grant cannot be revoked')
        self._retire()
        return True

    def _retire(self):
        delivery = self._delivery
        try:
            grant_unchanged = (json.dumps(self._grant, sort_keys=True, separators=(',', ':')) ==
                               self._grant_wire)
        except (TypeError, ValueError, RecursionError, OverflowError):
            grant_unchanged = False
        self._revoked = True
        incarnation, token = self._retired_identity
        delivery._retired_authority_incarnations.add(incarnation)
        delivery._retired_authority_tokens.add(token)
        owners = getattr(delivery, '_client_authority_selected_owners', {})
        if owners.get(self._connection_handle) is self:
            del owners[self._connection_handle]
        if not grant_unchanged:
            delivery._failed = True
            delivery._host._failed = True
            raise RuntimeError('authority grant changed during revocation')

    def _revoke_for_disconnect(self):
        self._retire()

    def _pull(self):
        d=self._delivery;host=d._host;host._check()
        host._control._reader_free()
        try:
            if self._failed or d._failed or self._request>=_MAX:raise RuntimeError('authority pull unavailable')
            members=d.membership();handles,peers=d._peers();incarnations=dict(d._incarnations)
            if self._connection_handle is None:
                if len(handles)!=1 or len(members)!=1:raise RuntimeError('one admitted authority participant required')
                h=handles[0]
            else:
                h=self._connection_handle
                owners=getattr(d,'_client_authority_selected_owners',None)
                if len(handles)>2 or h not in handles or type(owners) is not dict or owners.get(h) is not self:
                    raise RuntimeError('selected authority participant unavailable')
            if (self._grant['session_epoch']!=host._world.session.world_epoch or incarnations[h]!=self._grant['incarnation'] or
                {'id':'peer_'+str(h),'incarnation':incarnations[h]} not in members):
                raise RuntimeError('authority participant changed')
            host._control._reader_free()
        except BaseException:
            self._failed=True;d._failed=True;host._failed=True;raise
        lease=object();host._control._reader_lease=lease;host._busy=True;d._active=True;self._request+=1
        try:
            deadline=time.monotonic()+d._timeout
            def check():
                self._guarded()
                if (time.monotonic()>=deadline or self._failed or d._failed or host._failed or host._busy is not True or
                    d._active is not True or host._control._reader_lease is not lease or d._incarnations!=incarnations or
                    (self._connection_handle is not None and (self._connection_handle!=h or
                     getattr(d,'_client_authority_selected_owners',{}).get(h) is not self))):
                    raise RuntimeError('authority pull context changed')
            check();ExperimentalTCPParticipants._quiet(d,peers,deadline)
            request={'version':1,'kind':'authority_motion_pull','connection_handle':h,'session_epoch':host._world.session.world_epoch,
                     'incarnation':incarnations[h],'request_id':self._request,'grant':self._grant}
            base={k:request[k] for k in ('version','connection_handle','session_epoch','incarnation','request_id','grant')}
            def validate(answer):
                if type(answer) is not dict or set(answer)!=set(base)|{'kind','sample','sample_sha256'}:return False
                if (any(type(answer[k]) is not type(v) or answer[k]!=v for k,v in base.items()) or
                    json.dumps(answer['grant'],sort_keys=True,separators=(',',':'))!=self._grant_wire or
                    answer['kind']!='authority_motion_result'):return False
                if answer['sample'] is None:return answer['sample_sha256'] is None
                try:
                    sample=motion_value(answer['sample']);digest=motion_digest(sample)
                    return (answer['sample_sha256']==digest and sample['epoch']==self._grant['epoch'] and
                            sample['generation']==self._grant['generation'] and sample['index']==self._grant['index'] and
                            sample['sector_macro']==self._grant['sector_macro'] and sample['sequence']==self._last_sequence+1 and
                            (self._last_time is None and sample['velocity'] is None or
                             self._last_time is not None and sample['source_time']>self._last_time))
                except (TypeError,ValueError):return False
            raw=json.dumps(request,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')+b'\n'
            if len(raw)>MAX_MESSAGE+1:raise ValueError('authority pull frame too large')
            conn,peer=peers[h]
            others=[item[0] for handle,item in peers.items() if handle!=h]
            answer=ExperimentalTCPParticipants._exchange(d,conn,peer,others,raw,None,deadline,check=check,validate_answer=validate)
            check();current,current_peers=d._peers()
            if current!=handles or current_peers[h]!=peers[h] or d._incarnations!=incarnations:raise RuntimeError('authority participant changed')
            ExperimentalTCPParticipants._quiet(d,peers,deadline);check()
            if answer['sample'] is None:return None
            sample=motion_value(answer['sample']);self._last_sequence=sample['sequence'];self._last_time=sample['source_time']
            return sample
        except BaseException:
            self._failed=True;d._failed=True;host._failed=True;raise
        finally:
            changed=host._control._reader_lease is not lease
            if not changed:host._control._reader_lease=None
            else:self._failed=True;d._failed=True;host._failed=True
            d._active=False;host._busy=False
            if changed:raise RuntimeError('authority reader lease changed')
