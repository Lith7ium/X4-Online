#!/usr/bin/env python3
"""Trusted one-shot sender, configured only via inherited local socket FD."""
import json
import socket
import sys
import time
import authority_descriptor_loopback as wire


def main():
    if len(sys.argv) != 3:
        return 1
    tcp = socket.socket(fileno=int(sys.argv[1]))
    ipc = socket.socket(fileno=int(sys.argv[2]))
    try:
        ipc.settimeout(5)
        raw = bytearray()
        while True:
            chunk = ipc.recv(4097-len(raw))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > 4096:
                raise ValueError('oversized private configuration')
        data = json.loads(raw.decode('ascii'))
        if type(data) is not dict or set(data) != {'descriptor', 'deadline'}:
            raise ValueError('invalid private configuration')
        # The controller independently checks process and pause guards while
        # this helper waits. The absolute monotonic deadline is shared on Linux.
        wire.send_descriptor(tcp, data['descriptor'], data['deadline'], lambda: True)
        return 0
    except BaseException:
        return 1
    finally:
        ipc.close()
        tcp.close()


if __name__ == '__main__':
    sys.exit(main())
