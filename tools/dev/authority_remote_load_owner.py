#!/usr/bin/env python3
"""One isolated Linux load owner; supervisor supplies guarded X4 observations.

Owns the TCP socket until a claim is acknowledged. The final FD is sent over
private Unix IPC and the process exits; receiver must wait for successful exit
before using it. No game is started, observed, or authenticated here.
"""
import array
import json
import os
from pathlib import Path
import select
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
from authority.experimental_remote_load_client import ExperimentalRemoteLoadClient
from authority.trusted_load_messages import encode_bound_offer
from authority_tcp_native_worker import read_line, send_frame, parse_json


def run(tcp, ipc):
    if (tcp.family != socket.AF_INET or tcp.getsockname()[0] != '127.0.0.1' or
            tcp.getpeername()[0] != '127.0.0.1' or ipc.family != socket.AF_UNIX):
        raise ValueError('private loopback diagnostic sockets required')
    ipc.setblocking(False)
    config = parse_json(read_line(ipc, 16384, time.monotonic()+30))
    if (type(config) is not dict or set(config) != {'file_port','file_token','deadline','download','target'}):
        raise ValueError('invalid owner configuration')
    deadline = config['deadline']
    if type(deadline) not in (int,float) or not time.monotonic() < deadline < time.monotonic()+3600:
        raise ValueError('invalid owner deadline')
    target = Path(config['target'])
    if target.name != 'save_009.xml.gz' or not target.parent.is_dir() or any(target.parent.iterdir()):
        raise ValueError('expected empty private save directory')
    client = ExperimentalRemoteLoadClient(tcp, enabled=True, file_host='127.0.0.1',
        file_port=config['file_port'], file_token=config['file_token'], file_slot=1,
        deadline=deadline, io_timeout=300, keepalive_interval=1)
    transferred = None
    try:
        bound = client.request_offer()
        source = client.download(config['download'])
        # A private directory is required; no overwrite if a target appears.
        os.link(source, target, follow_symlinks=False)
        os.unlink(source)
        target.chmod(0o400)
        client.verify_staged(target)
        send_frame(ipc, json.dumps({'event':'staged','offer':encode_bound_offer(bound).decode('ascii')},
            separators=(',',':')).encode('ascii'), deadline, lambda: None)
        while True:
            client.poll()
            readable, _, bad = select.select([ipc], [], [ipc], min(.1, max(0, deadline-time.monotonic())))
            if bad: raise RuntimeError('supervisor IPC failure')
            if readable:
                command = parse_json(read_line(ipc, 256, deadline, client.poll))
                if command != {'command':'claim'}: raise ValueError('unexpected supervisor command')
                break
        attempt = bound.offer.attempt_id
        # Assertions are supplied only after supervisor observed real X4 events.
        client.load_requested(attempt)
        client.loaded_marker(attempt, bound.marker)
        client.paused(attempt, True)
        client.claim(attempt)
        transferred = client.take_connection()
        rights = array.array('i', [transferred.fileno()])
        if ipc.sendmsg([b'F'], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)]) != 1:
            raise RuntimeError('socket handoff failed')
    finally:
        if transferred is not None: transferred.close()
        client.close()


def main():
    if len(sys.argv) != 3: return 2
    sockets = []
    try:
        fds = [int(v) for v in sys.argv[1:]]
        if len(set(fds)) != 2 or min(fds) < 3: return 2
        sockets = [socket.socket(fileno=fd) for fd in fds]
        run(*sockets)
        return 0
    except BaseException:
        return 1
    finally:
        for sock in sockets: sock.close()

if __name__ == '__main__': sys.exit(main())
