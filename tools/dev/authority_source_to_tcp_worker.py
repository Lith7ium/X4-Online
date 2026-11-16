#!/usr/bin/env python3
"""One source X4 -> actual TCP -> client X4 diagnostic; no X4 starts here.

Both X4 instances, saves, process groups, logs, isolation and failure cleanup
belong to the outer supervisor. TCP admission/server checkpoint are synthetic;
the selected activation is not classified as a ship birth.
"""
import json
import math
from pathlib import Path
import re
import select
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_tcp_job_client_live as client_worker
from authority_tcp_native_worker import check_process, parse_json, read_line, send_frame
from authority_source_job_bind import bind_source, authorize_source
from authority.experimental_source_job_bridge import ExperimentalSourceJobBridge
from authority.local_participant_control import LocalParticipantControl

_TOKEN=re.compile(r'[0-9a-f]{32}\Z');_NAME=re.compile(r'[A-Za-z0-9_]{1,128}\Z')


def config(raw):
    c=parse_json(raw)
    required={'version','epoch','lease','attempt','generation','participant_lease','client_process','deadline',
              'job_epoch','source_lease','source_attempt','source_control_lease','source_world_epoch',
              'source_process','index','sectors'}
    if type(c) is not dict or set(c) not in (required,required|{'max_events'}) or type(c['version']) is not int or c['version']!=1:
        raise ValueError('invalid source worker configuration')
    if 'max_events' in c and (type(c['max_events']) is not int or not 2<=c['max_events']<=8):
        raise ValueError('invalid bounded event count')
    names=('epoch','lease','attempt','generation','participant_lease','job_epoch','source_lease',
           'source_attempt','source_control_lease')
    if (any(type(c[k]) is not str or not _TOKEN.fullmatch(c[k]) for k in (*names,'source_world_epoch')) or
        c['source_world_epoch']!=c['epoch'] or len({c[k] for k in names})!=len(names)):
        raise ValueError('invalid or overlapping worker contexts')
    if (type(c['index']) is not int or not 1<=c['index']<=9007199254740991-c.get('max_events',1)+1 or
        type(c['sectors']) is not list or not c['sectors'] or len(c['sectors'])>152 or
        any(type(v) is not str or not _NAME.fullmatch(v) for v in c['sectors']) or
        len(set(c['sectors']))!=len(c['sectors'])):
        raise ValueError('invalid selected entry or witnessed sectors')
    if (type(c['deadline']) not in (int,float) or not math.isfinite(c['deadline']) or
        not 40<c['deadline']-time.monotonic()<=600):raise ValueError('invalid source deadline')
    check_process(c['client_process']);check_process(c['source_process'])
    if c['client_process']['pid']==c['source_process']['pid']:raise ValueError('distinct owned X4 processes required')
    return c


class SelectedSourceBridge(ExperimentalSourceJobBridge):
    """Reject a foreign queue head or unavailable client sector before TCP."""
    def __init__(self,*args,expected_index,sectors,**kwargs):
        super().__init__(*args,**kwargs)
        self._expected_index=expected_index;self._sectors=frozenset(sectors)
    def _recv(self,deadline):
        row=super()._recv(deadline)
        if row and row[0]=='CANDIDATE':
            if (len(row)!=11 or row[1]!=self._epoch or row[2]!=self._generation or row[3]!=str(self._last+1) or
                row[4]!=str(self._expected_index+self._last) or row[7] not in self._sectors):
                raise ValueError('unexpected source queue head or no validated client witness')
        return row


def run(client_control,client_job,source_control,source_job,private,c):
    for sock in (client_control,client_job,source_control,source_job):client_worker.validate_udp(sock)
    addresses=[s.getsockname() for s in (client_control,client_job,source_control,source_job)]
    if len(set(addresses))!=4:raise ValueError('distinct local UDP ports required')
    source_identity=dict(c['source_process']);source_peer=None;source_control_peer=None
    def source_guard():
        check_process(source_identity)
        if source_peer is not None:
            if source_job.getpeername()!=source_peer or not client_worker.socket_owner(source_peer,source_job.getsockname(),source_identity):
                raise RuntimeError('source job UDP ownership changed')
        if source_control_peer is not None:
            if not client_worker.socket_owner(source_control_peer,source_control.getsockname(),source_identity):
                raise RuntimeError('source control UDP ownership changed')
        check_process(source_identity);return True
    def delivery_action(delivery,members,guard):
        nonlocal source_peer,source_control_peer
        source_control.settimeout(.1)
        expected=('HELLO|'+c['source_control_lease']+'|'+c['source_world_epoch']).encode('ascii')
        while source_control_peer is None:
            guard()
            try:packet,peer=source_control.recvfrom(769)
            except socket.timeout:continue
            if packet!=expected or not client_worker.socket_owner(peer,source_control.getsockname(),source_identity):
                raise RuntimeError('source control endpoint is not owned X4')
            source_control_peer=peer
        remaining=c['deadline']-time.monotonic()
        if remaining<=35:raise TimeoutError('insufficient source delivery budget')
        bound=bind_source(source_job,process=source_identity,lease=c['source_lease'],attempt=c['source_attempt'],
                          epoch=c['job_epoch'],generation=c['generation'],guard=guard,timeout=min(20,remaining-30))
        if bound is not source_job:raise RuntimeError('source socket handoff mismatch')
        source_peer=source_job.getpeername();guard()
        authorize_source(source_job,process=source_identity,lease=c['source_lease'],attempt=c['source_attempt'],
                         epoch=c['job_epoch'],generation=c['generation'],guard=guard,timeout=min(10,c['deadline']-time.monotonic()-30))
        remaining=c['deadline']-time.monotonic()
        if remaining<=35:raise TimeoutError('insufficient source bridge budget')
        bridge=SelectedSourceBridge(delivery,source_job,enabled=True,lease=c['source_lease'],attempt=c['source_attempt'],
            epoch=c['job_epoch'],generation=c['generation'],guard=guard,timeout=min(90,remaining-1),
            expected_index=c['index'],sectors=c['sectors'])
        ctl=LocalParticipantControl.__new__(LocalParticipantControl)
        ctl.sock=source_control;ctl.lease=c['source_control_lease'];ctl.peer=source_control_peer
        ctl.epoch=c['source_world_epoch'];ctl.handle=1;ctl.next_id=1;ctl.fault=False
        ctl.timeout=min(20,c['deadline']-time.monotonic()-30)
        if ctl.timeout<=0:raise TimeoutError('insufficient source resume budget')
        guard();ctl.resume((1,));guard()
        events=[]
        for seq in range(1,c.get('max_events',1)+1):
            detail=bridge.run_one();guard()
            if (detail.get('source_ack_observed') is not True or tuple(detail.get('members',()))!=tuple(members) or
                detail['event']['sequence']!=seq or detail['event']['index']!=c['index']+seq-1):
                raise RuntimeError('source job or source Ack differs')
            event=detail['event'];events.append({'event_sequence':event['sequence'],'index':event['index'],
                'sector_macro':event['descriptor']['sector_macro'],'macro':event['descriptor']['macro'],
                'faction':event['descriptor']['faction']})
        result={'event':'result','ok':True,'tcp_admitted':True,'tcp_job_receipt':True,'source_md_ack_observed':True,
                'client_md_ffi_asserted_by_owner':True,'synthetic_server_checkpoint_and_admission':True,
                'source_activation_is_birth':False,'descriptor_atomic':False,'frame_identity_proven':False}
        if 'max_events' in c:result['events']=events
        else:result.update(events[0])
        return result
    return client_worker.run(client_control,client_job,private,c,None,delivery_action=delivery_action,
                             extra_guard=source_guard,expected_jobs=c.get('max_events',1))


def main():
    if len(sys.argv)!=6:return 2
    try:
        client_control,client_job,source_control,source_job,private=(socket.socket(fileno=int(v)) for v in sys.argv[1:])
        c=config(read_line(private,16384,time.monotonic()+30))
        result=run(client_control,client_job,source_control,source_job,private,c)
        send_frame(private,json.dumps(result,separators=(',',':')).encode('ascii'),c['deadline'],
                   lambda:(check_process(c['source_process']),check_process(c['client_process'])))
        return 0
    except BaseException:
        try:private.sendall(b'{"event":"result","ok":false}\n')
        except BaseException:pass
        return 1

if __name__=='__main__':sys.exit(main())
