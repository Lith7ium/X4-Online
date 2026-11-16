"""Worker subprocess and loopback doubles only; no X4 execution."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from authority.experimental_client_load import HonestClientLoadClaim
from authority.load_messages import Receipt
from authority.trusted_load_messages import encode_load_claim

EPOCH='a'*32;LEASE='b'*32;ATTEMPT='c'*32

def line(sock):
    data=b''
    while not data.endswith(b'\n'):
        part=sock.recv(1)
        if not part: raise EOFError('socket closed')
        data+=part
        if len(data)>16384: raise ValueError('frame too large')
    return data[:-1]

def identity():
    path=Path('/proc')/str(os.getpid())
    fields=(path/'stat').read_text().rsplit(')',1)[1].split();image=(path/'exe').stat()
    return dict(pid=os.getpid(),start_ticks=int(fields[19]),exe_dev=image.st_dev,exe_ino=image.st_ino)

class WorkerTest(unittest.TestCase):
    def setUp(self):
        self.listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1',0));self.listener.listen(1);self.addCleanup(self.listener.close)
        client=socket.create_connection(self.listener.getsockname(),timeout=1)
        self.server,_=self.listener.accept();self.server.settimeout(2);self.addCleanup(self.server.close)
        udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0))
        self.engine=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.engine.bind(('127.0.0.1',0))
        self.engine.settimeout(2);self.addCleanup(self.engine.close)
        parent,child=socket.socketpair();parent.settimeout(2);self.ipc=parent;self.addCleanup(parent.close)
        self.proc=subprocess.Popen([sys.executable,str(ROOT/'tools/dev/authority_tcp_native_worker.py'),
                str(client.fileno()),str(udp.fileno()),str(child.fileno())],
                pass_fds=(client.fileno(),udp.fileno(),child.fileno()),
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        client.close();udp.close();child.close()
        self.addCleanup(self.cleanup)
        receipt=Receipt(EPOCH,1,1,1,ATTEMPT,'checkpoint-'+'d'*32,'e'*64,10)
        self.claim=encode_load_claim(HonestClientLoadClaim(receipt,'f'*32,True,True))
        self.cfg={'version':1,'claim':self.claim.decode('ascii'),'epoch':EPOCH,'handle':1,
                  'lease':LEASE,'udp_peer':list(self.engine.getsockname()),'udp_next_id':2,
                  'deadline':time.monotonic()+4,'controller_timeout':1,'client_process':identity()}

    def cleanup(self):
        if self.proc.poll() is None:
            self.proc.kill();self.proc.wait(timeout=2)

    def config(self): self.ipc.sendall(json.dumps(self.cfg,separators=(',',':')).encode()+b'\n')
    def claim_frame(self): self.assertEqual(line(self.server),self.claim)
    def ack(self,attempt=ATTEMPT,extra=b''):
        self.server.sendall(json.dumps({'version':1,'kind':'accepted','attempt_id':attempt}).encode()+b'\n'+extra)
    def event(self,kind): self.assertEqual(json.loads(line(self.ipc)),{'event':kind})
    def command(self,number=1,operation='resume'):
        return {'version':1,'kind':'participant_command','epoch':EPOCH,'connection_handle':1,
                'request_id':number,'operation':operation}
    def udp_reply(self,operation):
        msg,peer=self.engine.recvfrom(1024)
        self.assertEqual(msg,f'CMD|{LEASE}|{EPOCH}|2|{operation}'.encode())
        self.engine.sendto(f'RECEIPT|{LEASE}|{EPOCH}|2|{operation}|confirmed'.encode(),peer)

    def test_claim_ack_and_command_can_share_tcp_read_then_stop(self):
        self.config();self.claim_frame()
        cmd=self.command();raw=json.dumps(cmd,separators=(',',':')).encode()+b'\n'
        self.ack(extra=raw);self.event('active')
        self.udp_reply('resume')
        self.assertEqual(json.loads(line(self.server)),dict(cmd,kind='participant_receipt',status='confirmed'))
        self.ipc.sendall(b'{"command":"stop"}\n');self.event('stopped')
        self.assertEqual(self.proc.wait(timeout=2),0)

    def test_wrong_ack_faults_before_udp_dispatch(self):
        self.config();self.claim_frame();self.ack(attempt='0'*32)
        self.event('failed');self.assertEqual(self.proc.wait(timeout=2),1)
        self.engine.settimeout(.05)
        with self.assertRaises(socket.timeout):self.engine.recvfrom(1024)

    def test_admitted_handoff_does_not_resend_claim_and_accepts_queued_command(self):
        self.cfg['already_admitted']=True
        cmd=self.command();self.server.sendall(json.dumps(cmd).encode()+b'\n')
        self.config();self.event('active');self.udp_reply('resume')
        self.assertEqual(json.loads(line(self.server)),dict(cmd,kind='participant_receipt',status='confirmed'))
        self.ipc.sendall(b'{"command":"stop"}\n');self.event('stopped')
        self.assertEqual(self.proc.wait(timeout=2),0)

    def test_process_identity_mismatch_refuses_claim(self):
        self.cfg['client_process']['start_ticks']+=1
        self.config();self.event('failed');self.assertEqual(self.proc.wait(timeout=2),1)
        self.assertEqual(self.server.recv(1),b'')

    def test_udp_timeout_no_participant_receipt(self):
        self.cfg['controller_timeout']=.1
        self.config();self.claim_frame();self.ack();self.event('active')
        self.server.sendall(json.dumps(self.command()).encode()+b'\n')
        self.engine.recvfrom(1024)
        self.event('failed');self.assertEqual(self.proc.wait(timeout=2),1)
        self.assertEqual(self.server.recv(1),b'')

    def test_stop_during_local_control_fences_receipt(self):
        self.config();self.claim_frame();self.ack();self.event('active')
        self.server.sendall(json.dumps(self.command()).encode()+b'\n')
        msg,peer=self.engine.recvfrom(1024)
        self.assertEqual(msg,f'CMD|{LEASE}|{EPOCH}|2|resume'.encode())
        self.ipc.sendall(b'{"command":"stop"}\n')
        self.engine.sendto(f'RECEIPT|{LEASE}|{EPOCH}|2|resume|confirmed'.encode(),peer)
        self.event('failed');self.assertEqual(self.proc.wait(timeout=2),1)
        self.assertEqual(self.server.recv(1),b'')

    def test_stale_command_never_dispatched_twice(self):
        self.config();self.claim_frame();self.ack();self.event('active')
        data=json.dumps(self.command()).encode()+b'\n';self.server.sendall(data)
        self.udp_reply('resume');line(self.server)
        self.server.sendall(data);self.event('failed');self.assertEqual(self.proc.wait(timeout=2),1)
        self.engine.settimeout(.05)
        with self.assertRaises(socket.timeout):self.engine.recvfrom(1024)

if __name__=='__main__':unittest.main()
