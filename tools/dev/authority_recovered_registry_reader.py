#!/usr/bin/env python3
"""Read one checkpoint registry via a supervisor-owned private socket."""
import json
from pathlib import Path
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
    if type(config) is not dict or set(config) != {'checkpoint_id','path','sha256','size','marker'}:
        raise ValueError('invalid reader configuration')
    checkpoint = Checkpoint(config['checkpoint_id'], Path(config['path']), config['sha256'], config['size'], config['marker'])
    status = saved_status(checkpoint)
    payload = json.dumps({'status':status}, separators=(',', ':')).encode('ascii')
    send_frame(sock, payload, time.monotonic()+30, lambda:None)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2: raise ValueError('private socket required')
        with socket.socket(fileno=int(sys.argv[1])) as channel: run(channel)
    except BaseException:
        sys.exit(1)
