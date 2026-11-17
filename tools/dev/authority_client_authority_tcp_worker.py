#!/usr/bin/env python3
"""Bounded opt-in client-to-server read-only diagnostic; never starts X4.

Admission/checkpoint are synthetic. The external supervisor owns locks,
processes, staging, test-grant proof, fencing and cleanup on all outcomes.
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
import authority_tcp_job_client_live as client
from authority_tcp_native_worker import check_process,parse_json,read_line,send_frame
from authority.experimental_tcp_client_authority_motion import ExperimentalTCPClientAuthorityMotion
from authority.experimental_motion_pair_evidence import validate_pair

SECTOR='cluster_115_sector001_macro'
INDEX=1318
_TOKEN=re.compile(r'[0-9a-f]{32}\Z')
_FIELDS={'version','epoch','lease','attempt','generation','participant_lease','job_epoch','client_process','server_process','deadline','authority_lease','authority_attempt','incarnation','grant_token','sample_count'}
_TOKENS=('epoch','lease','attempt','generation','participant_lease','job_epoch','authority_lease','authority_attempt','incarnation','grant_token')

def config(raw):
    c=parse_json(raw)
    if (type(c) is not dict or set(c)-{'include_orientation'}!=_FIELDS or type(c['version']) is not int or c['version']!=1 or
        type(c.get('include_orientation',False)) is not bool):
        raise ValueError('invalid authority worker config')
    if any(type(c[k]) is not str or not _TOKEN.fullmatch(c[k]) for k in _TOKENS) or len({c[k] for k in _TOKENS})!=len(_TOKENS):
        raise ValueError('invalid authority context tokens')
    if (type(c['deadline']) not in (int,float) or not math.isfinite(c['deadline']) or
        not 10<c['deadline']-time.monotonic()<=600 or type(c['sample_count']) is not int or c['sample_count'] not in (1,2)):
        raise ValueError('invalid authority operation bounds')
    check_process(c['client_process']);check_process(c['server_process'])
    if c['client_process']['pid']==c['server_process']['pid']:raise ValueError('distinct X4 processes required')
    return c

def run(participant_udp,job_udp,authority_udp,private,c):
    identity=dict(c['server_process'])
    grant={'session_epoch':c['epoch'],'epoch':c['job_epoch'],'generation':c['generation'],'index':INDEX,
           'sector_macro':SECTOR,'token':c['grant_token'],'incarnation':c['incarnation']}
    def server_guard():
        check_process(identity)
        return True
    def action(delivery,members,guard):
        if len(members)!=1 or members[0]['incarnation']!=c['incarnation']:
            raise RuntimeError('test incarnation not admitted')
        owner=ExperimentalTCPClientAuthorityMotion(delivery,enabled=True,grant=grant,guard=lambda v:guard() and v==grant)
        samples=[]
        while len(samples)<c['sample_count']:
            guard();sample=owner.pull();guard()
            if sample is not None:samples.append(sample)
            else:
                # Avoid a hot TCP/UDP loop while the running source has no
                # newer game-time sample. Parent-control input interrupts wait.
                select.select([private],[],[private],min(.05,max(0,c['deadline']-time.monotonic())))
                guard()
        if len(samples)==2:
            samples=validate_pair(samples,epoch=c['job_epoch'],generation=c['generation'],index=INDEX,sector=SECTOR)
        return {'event':'result','ok':True,'tcp_admitted':True,'synthetic_server_checkpoint_and_admission':True,
                'client_authority_registered':True,'index':INDEX,'sector_macro':SECTOR,'samples':samples,
                'server_x4_motion_applied':False,'frame_identity_proven':False}
    return client.run(participant_udp,job_udp,private,c,None,delivery_action=action,extra_guard=server_guard,
                      expected_jobs=None,authority_udp=authority_udp,authority_grant=grant)

def main():
    if len(sys.argv)!=5:return 2
    private=None
    try:
        participant,job,authority,private=(socket.socket(fileno=int(v)) for v in sys.argv[1:])
        c=config(read_line(private,16384,time.monotonic()+30));result=run(participant,job,authority,private,c)
        send_frame(private,json.dumps(result,separators=(',',':'),allow_nan=False).encode('ascii'),c['deadline'],
                   lambda:(check_process(c['client_process']),check_process(c['server_process'])))
        return 0
    except BaseException:
        try:
            if private is not None:private.sendall(b'{"event":"result","ok":false}\n')
        except BaseException:pass
        return 1
if __name__=='__main__':sys.exit(main())
