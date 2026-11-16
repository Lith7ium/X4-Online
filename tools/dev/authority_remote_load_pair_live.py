#!/usr/bin/env python3
"""Opt-in Linux two-X4 remote-load owner diagnostic. Never starts X4 on import.

The existing isolated two-X4 supervisor protects the processes, ticket, staged
save, and ordered marker/pause observations. A separate owner executes the
real remote load client and keeps it alive while the host is pumped. This is
not a Windows, Internet, or gameplay test.
"""
import argparse
import array
import json
from pathlib import Path
import select
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_tcp_native_live as native
from authority.experimental_client_load import ExperimentalClientLoad
from authority.trusted_load_messages import decode_bound_offer
from authority_helper_lifecycle import OwnedHelper


class RemoteParticipant(native.TCPMarkedParticipant):
    def join(self, world):
        handle = super().join(world)
        self.control._keepalive_enabled = True
        return handle

    def pump_loading(self):
        if self.remote_helper.proc.poll() is not None:
            raise RuntimeError('remote load owner exited during X4 load')
        self.control.poll(0)
        if self.server_tcp not in self.control._peers:
            raise RuntimeError('remote load control disconnected')

    def wait_ipc(self, deadline):
        while True:
            self.pump_loading()
            if select.select([self.remote_ipc], [], [], 0)[0]:
                return native.read_line(self.remote_ipc, deadline, maximum=16384)
            native.marked.remaining(deadline)
            time.sleep(.01)

    def offer_and_download(self, world, service, handle, out, profile):
        if any((profile/'save').iterdir()): raise ValueError('private save directory is not empty')
        self.remote_ipc, child = socket.socketpair()
        try:
            self.remote_helper = OwnedHelper([sys.executable, str(ROOT/'tools/dev/authority_remote_load_owner.py'),
                str(self.client_tcp.fileno()), str(child.fileno())], registry=self.helpers,
                pass_fds=(self.client_tcp.fileno(), child.fileno()))
            child.close()
            self.client_tcp.close(); self.client_tcp = None
            target = profile/'save'/native.marked.base.snapshot.SLOT
            config = {'file_port':service.port, 'file_token':service.token, 'deadline':self.run_deadline,
                      'download':str(out/'download'), 'target':str(target)}
            self.remote_ipc.settimeout(min(1, native.marked.remaining(self.run_deadline)))
            self.remote_ipc.sendall(json.dumps(config, separators=(',',':')).encode('ascii')+b'\n')
            self.remote_helper.release()
            event = json.loads(self.wait_ipc(self.run_deadline))
            if type(event) is not dict or set(event) != {'event','offer'} or event['event'] != 'staged':
                raise ValueError('invalid remote load event')
            bound = decode_bound_offer(event['offer'].encode('ascii'))
            self.offer, self.marker = bound.offer, bound.marker
            save = world._load_offers[handle].save
            if (bound.offer.connection_handle != handle or bound.offer.checkpoint_id != save.checkpoint_id or
                bound.offer.sha256 != save.sha256 or bound.offer.size != save.size or bound.offer.name != save.name):
                raise ValueError('TCP offer differs from coordinator')
            self.client_load = ExperimentalClientLoad(enabled=True, offer=self.offer, expected_marker=self.marker)
            self.client_load.verify_staged(target, pump=self.pump_loading)
            ticket = {key:getattr(self.offer,key) for key in native.marked.base.client.FIELDS if key != 'slot'}
            ticket['slot']='save_009'; self.ticket=dict(ticket)
            return ticket, target
        finally:
            child.close()

    def finish_remote_load(self, guard, deadline):
        # Caller has just checked actual ordered load, marker and pause receipts,
        # both X4 identities and protected files; no fabricated event is sent.
        guard()
        self.remote_ipc.sendall(b'{"command":"claim"}\n')
        while True:
            guard(); self.control.poll(0)
            if select.select([self.remote_ipc], [], [], 0)[0]: break
            if self.remote_helper.proc.poll() is not None:
                raise RuntimeError('remote load owner exited before socket handoff')
            native.marked.remaining(deadline); time.sleep(.01)
        data, ancillary, flags, _ = self.remote_ipc.recvmsg(1, socket.CMSG_SPACE(array.array('i').itemsize))
        fds=[]
        try:
            for level, kind, payload in ancillary:
                if level != socket.SOL_SOCKET or kind != socket.SCM_RIGHTS:
                    raise ValueError('unexpected handoff control message')
                values=array.array('i'); values.frombytes(payload[:len(payload)-(len(payload)%values.itemsize)])
                fds.extend(values)
            if data != b'F' or flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC) or len(fds)!=1:
                raise ValueError('invalid socket handoff')
            # The sender no longer owns or uses TCP after successful exit.
            while self.remote_helper.proc.poll() is None:
                guard(); self.control.poll(0); native.marked.remaining(deadline); time.sleep(.01)
            if self.remote_helper.proc.returncode != 0: raise RuntimeError('remote owner failed after handoff')
            guard()
            conn=socket.socket(fileno=fds.pop())
            if conn.family != socket.AF_INET or conn.getpeername()[0] != '127.0.0.1':
                conn.close(); raise ValueError('handoff socket changed')
            return conn
        finally:
            for fd in fds:
                import os
                os.close(fd)

    def cleanup_before_owned_processes(self):
        try:
            return super().cleanup_before_owned_processes()
        finally:
            ipc=getattr(self, 'remote_ipc', None)
            if ipc is not None: ipc.close()


def run(args):
    participant=RemoteParticipant(time.monotonic()+args.timeout, first_resume_only=True)
    original=native.marked.MarkedParticipant
    try:
        native.marked.MarkedParticipant=lambda:participant
        result=native.marked.run(args)
    finally:
        native.marked.MarkedParticipant=original
    result['scope']='isolated Linux two-X4 remote-load-owner loopback diagnostic; no Windows, Internet or gameplay'
    (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--display',required=True);parser.add_argument('--timeout',type=float,default=600)
    parser.add_argument('--seed',type=int,default=276944566)
    result=run(parser.parse_args())
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__': sys.exit(main())
