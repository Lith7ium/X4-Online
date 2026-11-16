#!/usr/bin/env python3
"""Read one checkpoint registry via a supervisor-owned private socket."""
import json
import math
from pathlib import Path
import re
import select
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
from authority.checkpoints import Checkpoint
from authority_recovery_registry_status import saved_status
from authority_tcp_native_worker import parse_json, read_line, send_frame


def run(sock):
    if sock.family != socket.AF_UNIX or sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM:
        raise ValueError('private stream required')
    sock.setblocking(False)
    config = parse_json(read_line(sock, 4096, time.monotonic()+30))
    if type(config) is dict and config.get('mode') == 'witness_guard':
        return run_guard(sock,config)
    if type(config) is not dict or set(config) != {'checkpoint_id','path','sha256','size','marker'}:
        raise ValueError('invalid reader configuration')
    checkpoint = Checkpoint(config['checkpoint_id'], Path(config['path']), config['sha256'], config['size'], config['marker'])
    status = saved_status(checkpoint)
    payload = json.dumps({'status':status}, separators=(',', ':')).encode('ascii')
    send_frame(sock, payload, time.monotonic()+30, lambda:None)


def run_guard(sock, config):
    """Own one fully validated checkpoint guard until correlated STOP/EOF."""
    from authority.checkpoints import CheckpointStore
    from authority_witness_source_guard import WitnessSourceGuard
    if (set(config)!={'mode','checkpoint_id','path','sha256','size','marker','store','token','deadline'} or
        type(config['token']) is not str or not re.fullmatch(r'[0-9a-f]{32}',config['token']) or
        type(config['deadline']) not in (int,float) or not math.isfinite(config['deadline']) or
        not time.monotonic()<config['deadline']<=time.monotonic()+86400):
        raise ValueError('invalid guard configuration')
    deadline=config['deadline'];token=config['token']
    checkpoint=Checkpoint(config['checkpoint_id'],Path(config['path']),config['sha256'],config['size'],config['marker'])
    guard=WitnessSourceGuard(CheckpointStore(config['store']),checkpoint)
    if time.monotonic()>=deadline:raise TimeoutError('guard initialization expired')
    def reply(data):
        send_frame(sock,json.dumps(data,separators=(',',':')).encode('ascii'),deadline,lambda:None)
    reply({'token':token,'seq':0,'event':'READY','status':guard.status})
    seq=0
    while True:
        request=parse_json(read_line(sock,512,deadline))
        if (type(request) is not dict or set(request)!={'token','seq','op'} or request['token']!=token or
            type(request['seq']) is not int or request['seq']!=seq+1 or request['op'] not in ('CHECK','STOP')):
            raise ValueError('invalid guard request')
        seq+=1
        if request['op']=='STOP':
            guard.check()
            reply({'token':token,'seq':seq,'event':'STOPPED'})
            # Retain the process until the owner has consumed STOPPED and
            # explicitly half-closed its write side. No further request is valid.
            while True:
                left=deadline-time.monotonic()
                if left<=0:raise TimeoutError('guard STOP acknowledgement timed out')
                ready,_,bad=select.select([sock],[],[sock],min(.25,left))
                if bad:raise RuntimeError('guard IPC failed')
                if ready:
                    if sock.recv(1)!=b'':raise ValueError('unexpected frame after STOP')
                    break
            return
        if guard.check() is not True:raise ValueError('guard failed')
        reply({'token':token,'seq':seq,'event':'CHECKED'})


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2: raise ValueError('private socket required')
        with socket.socket(fileno=int(sys.argv[1])) as channel: run(channel)
    except BaseException:
        sys.exit(1)
