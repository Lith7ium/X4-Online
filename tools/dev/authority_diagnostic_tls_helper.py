#!/usr/bin/env python3
"""Owned local TLS gateway for the recovered-X4 diagnostic only."""
import asyncio
import json
from pathlib import Path
import socket
import ssl
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from authority.experimental_tls_tunnel import (
    relay_connected_client, relay_connected_server, start_client, start_server,
)


async def serve(ipc, raw_socket, tls_socket, listeners, config):
    key = bytes.fromhex(config['shared_key'])
    if len(key) != 32:
        raise ValueError('invalid session key')
    if config['role'] == 'server':
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(config['certificate'], config['private_key'])
        tunnel = await start_server(listener=listeners[0], ssl_context=context,
            shared_key=key, control_port=config['unused_port'], file_port=config['file_port'])
        relay = relay_connected_server(tls_socket=tls_socket, backend_socket=raw_socket,
                                       ssl_context=context, shared_key=key)
    elif config['role'] == 'client':
        tunnel = await start_client(control_listener=listeners[0], file_listener=listeners[1],
            server_host='127.0.0.1', server_port=config['server_port'],
            server_fingerprint=config['fingerprint'], shared_key=key)
        relay = relay_connected_client(raw_socket=raw_socket, tls_socket=tls_socket,
            server_hostname='127.0.0.1', server_fingerprint=config['fingerprint'], shared_key=key)
    else:
        raise ValueError('unknown helper role')
    loop = asyncio.get_running_loop()
    ipc.setblocking(False)
    relay_task = asyncio.create_task(relay)
    tunnel_task = asyncio.create_task(tunnel.wait())
    ipc_task = asyncio.create_task(loop.sock_recv(ipc, 1))
    tasks = [relay_task, tunnel_task, ipc_task]
    try:
        await loop.sock_sendall(ipc, b'R')
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        if relay_task not in done:
            raise RuntimeError('gateway control channel ended')
        relay_task.result()
        await loop.sock_sendall(ipc, b'D')
        await asyncio.wait([tunnel_task, ipc_task], return_when=asyncio.FIRST_COMPLETED)
        raise RuntimeError('gateway control channel ended')
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await tunnel.close()


def main():
    sockets = []
    try:
        fds = [int(value) for value in sys.argv[1:]]
        if len(fds) not in (4, 5) or len(set(fds)) != len(fds):
            raise ValueError('invalid inherited descriptors')
        sockets = [socket.socket(fileno=fd) for fd in fds]
        ipc, raw_socket, tls_socket, *listeners = sockets
        ipc.settimeout(10)
        config = json.loads(ipc.recv(16384))
        asyncio.run(serve(ipc, raw_socket, tls_socket, listeners, config))
    except BaseException:
        return 1
    finally:
        for sock in sockets:
            sock.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
