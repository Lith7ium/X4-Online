#!/usr/bin/env python3
"""Trusted one-shot job sender; private config and TCP are inherited FDs."""
import json
import socket
import sys
import authority_job_descriptor_loopback as wire


def main():
    if len(sys.argv)!=3:return 1
    tcp=socket.socket(fileno=int(sys.argv[1]));ipc=socket.socket(fileno=int(sys.argv[2]))
    try:
        ipc.settimeout(5);raw=bytearray()
        while True:
            part=ipc.recv(4097-len(raw))
            if not part:break
            raw.extend(part)
            if len(raw)>4096:raise ValueError('private configuration too large')
        config=json.loads(raw.decode('ascii'))
        if type(config) is not dict or set(config)!={'descriptor','deadline'}:raise ValueError('invalid config')
        # The supervisor independently fences X4/process state while we wait.
        wire.send_descriptor(tcp,config['descriptor'],config['deadline'],lambda:True)
        return 0
    except BaseException:return 1
    finally:ipc.close();tcp.close()

if __name__=='__main__':sys.exit(main())
