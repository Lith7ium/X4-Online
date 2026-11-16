#!/usr/bin/env python3
"""Private, explicitly configured one-shot client-to-server X4 diagnostic.

The supervisor owns both disposable X4 processes, their staged files and all
cleanup. Admission and authority are test assumptions. No job is delivered.
"""
import json
import math
import socket
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_client_authority_tcp_worker as base
import authority_tcp_job_client_live as client
from authority_tcp_native_worker import check_process,parse_json,read_line,send_frame
from authority.experimental_tcp_client_authority_motion import ExperimentalTCPClientAuthorityMotion
from authority.experimental_motion_pair_evidence import validate_pair
from authority.experimental_participant_job_ipc import ExperimentalParticipantJobIPC
from authority.experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC
from authority.local_participant_control import LocalParticipantControl
from authority.experimental_tcp_motion import motion_value

EXTRA=('server_participant_lease','server_job_lease','server_job_attempt','server_motion_lease','server_motion_attempt')
SNAPSHOT_FIELDS={'role','nonce','epoch','index','code','macro','faction','sector_macro','game_time','position'}

def snapshot_value(value,epoch):
    if (type(value) is not dict or set(value)!=SNAPSHOT_FIELDS or value['role']!='server' or
        type(value['nonce']) is not str or not base._TOKEN.fullmatch(value['nonce']) or value['epoch']!=epoch or
        type(value['index']) is not int or value['index']!=base.INDEX or value['code']!='WRG-830' or
        value['macro']!='ship_ter_m_corvette_01_a_macro' or value['faction']!='pioneers' or value['sector_macro']!=base.SECTOR or
        type(value['game_time']) not in (int,float) or not math.isfinite(value['game_time']) or value['game_time']<0 or
        type(value['position']) is not list or len(value['position'])!=3 or
        any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1e9 for x in value['position'])):
        raise ValueError('invalid local server frame observation')
    return {**value,'position':list(value['position'])}

def sample_series(samples,epoch,generation):
    if type(samples) is not list or not 1<=len(samples)<=12:raise ValueError('invalid candidate samples')
    out=[motion_value(s) for s in samples]
    for n,v in enumerate(out,1):
        if (v['epoch']!=epoch or v['generation']!=generation or v['index']!=base.INDEX or
            v['sequence']!=n or v['sector_macro']!=base.SECTOR):raise ValueError('foreign candidate')
        if n==1:
            if v['velocity'] is not None:raise ValueError('first velocity must be unknown')
        else:
            before=out[n-2];dt=v['source_time']-before['source_time']
            if not math.isfinite(dt) or dt<=0:raise ValueError('candidate time did not advance')
            if v['velocity'] is not None:
                if not .02<=dt<=1:raise ValueError('candidate velocity interval differs')
                for k in ('x','y','z'):
                    if not math.isclose(v['velocity'][k],(v[k]-before[k])/dt,rel_tol=1e-9,abs_tol=1e-9):
                        raise ValueError('candidate velocity differs')
    return out

def config(raw):
    c=parse_json(raw)
    if type(c) is not dict or set(c)!=base._FIELDS|set(EXTRA)|{'server_snapshot'}:raise ValueError('invalid apply config')
    b={k:c[k] for k in base._FIELDS};base.config(json.dumps(b).encode())
    if c['sample_count']!=2 or any(type(c[k]) is not str or not base._TOKEN.fullmatch(c[k]) for k in EXTRA):
        raise ValueError('invalid apply context')
    tokens=[c[k] for k in base._TOKENS+EXTRA]
    if len(set(tokens))!=len(tokens):raise ValueError('reused apply token')
    snapshot=snapshot_value(c['server_snapshot'],c['job_epoch'])
    if snapshot['nonce'] in tokens:raise ValueError('reused frame nonce')
    c['server_snapshot']=snapshot
    return c

def run(cc,cj,ca,sc,sj,sm,private,c):
    sockets=(cc,cj,ca,sc,sj,sm)
    for s in sockets:client.validate_udp(s)
    if len({s.getsockname() for s in sockets})!=len(sockets):raise ValueError('distinct UDP sockets required')
    identity=dict(c['server_process'])
    grant={'session_epoch':c['epoch'],'epoch':c['job_epoch'],'generation':c['generation'],'index':base.INDEX,
           'sector_macro':base.SECTOR,'token':c['grant_token'],'incarnation':c['incarnation']}
    def server_guard():check_process(identity);return True
    def action(delivery,members,guard):
        if len(members)!=1 or members[0]['incarnation']!=c['incarnation']:raise RuntimeError('wrong admitted peer')
        selection_deadline=min(c['deadline'],time.monotonic()+20)
        def selection_guard():
            guard()
            if time.monotonic()>=selection_deadline:raise TimeoutError('candidate window exhausted')
            return True
        owner=ExperimentalTCPClientAuthorityMotion(delivery,enabled=True,grant=grant,guard=lambda v:selection_guard() and v==grant)
        samples=[];candidate=None;distance=None
        while len(samples)<12:
            selection_guard();v=owner.pull();selection_guard()
            if v is not None:
                samples.append(v);samples=sample_series(samples,c['job_epoch'],c['generation'])
                distance=math.dist(c['server_snapshot']['position'],[v[k] for k in ('x','y','z')])
                if not math.isfinite(distance):raise ValueError('invalid candidate distance')
                if 5<=distance<=50:candidate=samples[-1];break
            else:
                import select
                select.select([private],[],[private],min(.05,max(0,selection_deadline-time.monotonic())));selection_guard()
        if candidate is None:raise RuntimeError('no candidate in bounded window')
        selection_guard()
        # Resume follows selection; only a point-in-time pause was observed.
        sc.settimeout(.1);expected=('HELLO|'+c['server_participant_lease']+'|'+c['epoch']).encode()
        while True:
            selection_guard()
            try:data,peer=sc.recvfrom(769)
            except socket.timeout:continue
            if data!=expected or not client.socket_owner(peer,sc.getsockname(),identity):raise RuntimeError('wrong server control peer')
            break
        def peer_guard(p,s):
            guard();ok=client.socket_owner(p,s.getsockname(),identity);guard();return ok
        ctl=LocalParticipantControl.__new__(LocalParticipantControl)
        ctl.sock=sc;ctl.lease=c['server_participant_lease'];ctl.peer=peer;ctl.epoch=c['epoch'];ctl.handle=1
        ctl.next_id=1;ctl.fault=False;ctl.timeout=min(20,c['deadline']-time.monotonic()-5)
        selection_guard()
        if ctl.timeout<=0 or not peer_guard(peer,sc):raise RuntimeError('server control peer changed')
        selection_guard()
        if ctl.resume((1,)) is not True or not peer_guard(peer,sc):
            raise RuntimeError('server resume not confirmed')
        timeout=min(20,c['deadline']-time.monotonic()-5)
        if timeout<=0:raise TimeoutError('server operation budget exhausted')
        job=ExperimentalParticipantJobIPC(sj,enabled=True,lease=c['server_job_lease'],attempt=c['server_job_attempt'],
            epoch=c['job_epoch'],generation=c['generation'],guard=guard,validate_peer=lambda p:peer_guard(p,sj),timeout=timeout)
        motion=ExperimentalParticipantMotionIPC(sm,enabled=True,lease=c['server_motion_lease'],attempt=c['server_motion_attempt'],
            epoch=c['job_epoch'],generation=c['generation'],guard=guard,validate_peer=lambda p:peer_guard(p,sm),timeout=timeout,allow_apply=True)
        try:
            job.wait_ready();motion.wait_ready();guard()
            if motion(candidate,False) is not True:raise RuntimeError('server bind failed')
            if motion.preflight(candidate)!='READY':raise RuntimeError('server preflight not ready')
            guard()
            if motion.apply_once(candidate) is not True:raise RuntimeError('server apply not confirmed')
            guard()
        finally:
            job.close();motion.close()
        return {'event':'result','ok':True,'tcp_admitted':True,'synthetic_server_checkpoint_and_admission':True,
            'client_authority_registered':True,'index':base.INDEX,'sector_macro':base.SECTOR,'samples':samples,
            'server_x4_motion_applied':True,'server_apply_receipt':True,'frame_identity_proven':False,
            'server_snapshot':c['server_snapshot'],'candidate_distance':distance,'selected_sequence':candidate['sequence']}
    return client.run(cc,cj,private,c,None,delivery_action=action,extra_guard=server_guard,
        expected_jobs=None,authority_udp=ca,authority_grant=grant)

def main():
    if len(sys.argv)!=8:return 2
    private=None
    try:
        cc,cj,ca,sc,sj,sm,private=(socket.socket(fileno=int(v)) for v in sys.argv[1:])
        c=config(read_line(private,16384,time.monotonic()+30));result=run(cc,cj,ca,sc,sj,sm,private,c)
        send_frame(private,json.dumps(result,separators=(',',':'),allow_nan=False).encode('ascii'),c['deadline'],
                   lambda:(check_process(c['client_process']),check_process(c['server_process'])))
        return 0
    except BaseException:
        try:
            if private is not None:private.sendall(b'{"event":"result","ok":false}\n')
        except BaseException:pass
        return 1
if __name__=='__main__':sys.exit(main())
