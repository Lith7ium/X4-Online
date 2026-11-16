"""Loopback process handoff tests; X4 observations are simulated by the test."""
import array
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.load_messages import Offer
from authority.trusted_load_messages import encode_bound_offer, decode_load_claim
from authority.trusted_marker_load_session import MarkerBoundOffer
from lockstep.launcher.joinfiles import FileService
import authority_remote_load_pair_live as pair


class OwnerTest(unittest.TestCase):
    def test_overlong_owner_deadline_is_rejected_before_offer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'save').mkdir()
            listener=socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen()
            tcp=socket.create_connection(listener.getsockname()); server,_=listener.accept(); listener.close()
            parent,child=socket.socketpair();proc=None
            try:
                proc=subprocess.Popen([sys.executable,str(ROOT/'tools/dev/authority_remote_load_owner.py'),
                    str(tcp.fileno()),str(child.fileno())],pass_fds=(tcp.fileno(),child.fileno()))
                tcp.close();child.close()
                config={'file_port':1,'file_token':'a'*32,'deadline':time.monotonic()+4000,
                        'download':str(root/'download'),'target':str(root/'save/save_009.xml.gz')}
                parent.sendall(json.dumps(config).encode()+b'\n')
                self.assertEqual(proc.wait(timeout=4),1)
                server.settimeout(2); self.assertEqual(server.recv(1),b'')
                self.assertFalse((root/'download').exists())
            finally:
                parent.close();child.close();tcp.close();server.close()
                if proc is not None and proc.poll() is None: proc.kill();proc.wait()

    def test_helper_deadline_never_extends_owner_or_accepts_expired(self):
        now=time.monotonic()
        self.assertEqual(pair.remote_owner_deadline(now+20),now+20)
        bounded=pair.remote_owner_deadline(now+4000)
        self.assertLess(bounded,time.monotonic()+3600)
        self.assertLessEqual(bounded,now+4000)
        for value in (now-1, float('nan'), float('inf'), True):
            with self.subTest(value=value), self.assertRaises(TimeoutError):
                pair.remote_owner_deadline(value)

    def test_invalid_supervisor_command_never_sends_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'save').mkdir(); data=b'other-test-save'
            source=root/'source'; source.write_bytes(data)
            service=FileService('a'*32,slots=(1,)).start(); self.addCleanup(service.close)
            service.offer('j1.xml.gz',source)
            offer=Offer(world_epoch='epoch',connection_handle=1,baseline_id=1,load_generation=1,
                attempt_id='c'*32,checkpoint_id='checkpoint-'+'d'*32,sha256=hashlib.sha256(data).hexdigest(),
                size=len(data),name='j1.xml.gz')
            listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen()
            tcp=socket.create_connection(listener.getsockname());server,_=listener.accept();listener.close()
            parent,child=socket.socketpair(); errors=[]; received=[]
            def host():
                try:
                    server.settimeout(5)
                    with server, server.makefile('rb') as stream:
                        stream.readline()
                        server.sendall(encode_bound_offer(MarkerBoundOffer(offer,'b'*32))+b'\n')
                        received.append(stream.readline())
                except BaseException as error: errors.append(error)
            thread=threading.Thread(target=host);thread.start()
            proc=subprocess.Popen([sys.executable,str(ROOT/'tools/dev/authority_remote_load_owner.py'),
                                   str(tcp.fileno()),str(child.fileno())],pass_fds=(tcp.fileno(),child.fileno()))
            tcp.close();child.close();self.addCleanup(lambda:proc.kill() if proc.poll() is None else None)
            parent.settimeout(5)
            cfg={'file_port':service.port,'file_token':'a'*32,'deadline':time.monotonic()+6,
                 'download':str(root/'download'),'target':str(root/'save/save_009.xml.gz')}
            parent.sendall(json.dumps(cfg).encode()+b'\n')
            with parent.makefile('rb',buffering=0) as reader:
                self.assertEqual(json.loads(reader.readline())['event'],'staged')
            parent.sendall(b'{"command":"claim-without-observation"}\n')
            self.assertEqual(proc.wait(timeout=4),1);parent.close()
            thread.join(4);self.assertFalse(thread.is_alive());self.assertFalse(errors)
            self.assertEqual(received,[b''])

    def test_transfer_keepalive_and_single_socket_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'save').mkdir(); data=b'private-test-save'
            source=root/'source'; source.write_bytes(data)
            token='a'*32; marker='b'*32
            service=FileService(token,slots=(1,)).start(); self.addCleanup(service.close)
            service.offer('j1.xml.gz',source)
            offer=Offer(world_epoch='epoch',connection_handle=1,baseline_id=1,load_generation=1,
                attempt_id='c'*32,checkpoint_id='checkpoint-'+'d'*32,sha256=hashlib.sha256(data).hexdigest(),
                size=len(data),name='j1.xml.gz')
            listener=socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen()
            tcp=socket.create_connection(listener.getsockname()); server,_=listener.accept(); listener.close()
            parent,child=socket.socketpair(); errors=[]; keep=[]; claimed=[]
            def host():
                try:
                    server.settimeout(8)
                    with server, server.makefile('rb') as stream:
                        self.assertEqual(json.loads(stream.readline())['kind'],'offer_request')
                        server.sendall(encode_bound_offer(MarkerBoundOffer(offer,marker))+b'\n')
                        while True:
                            row=stream.readline()
                            obj=json.loads(row)
                            if obj.get('kind')!='keepalive': break
                            keep.append(obj['sequence'])
                            server.sendall(json.dumps({'version':1,'kind':'alive','attempt_id':offer.attempt_id,
                                                       'sequence':obj['sequence']}).encode()+b'\n')
                        claimed.append(decode_load_claim(row.rstrip(b'\n')))
                        server.sendall(json.dumps({'version':1,'kind':'accepted','attempt_id':offer.attempt_id}).encode()+b'\n')
                        self.assertEqual(stream.readline(), b'from-handoff\n')
                except BaseException as error: errors.append(error)
            thread=threading.Thread(target=host);thread.start()
            proc=subprocess.Popen([sys.executable,str(ROOT/'tools/dev/authority_remote_load_owner.py'),
                                   str(tcp.fileno()),str(child.fileno())],pass_fds=(tcp.fileno(),child.fileno()))
            tcp.close();child.close();self.addCleanup(lambda:proc.kill() if proc.poll() is None else None)
            parent.settimeout(6)
            cfg={'file_port':service.port,'file_token':token,'deadline':pair.remote_owner_deadline(time.monotonic()+4000),
                 'download':str(root/'download'),'target':str(root/'save/save_009.xml.gz')}
            parent.sendall(json.dumps(cfg).encode()+b'\n')
            with parent.makefile('rb',buffering=0) as reader:
                event=json.loads(reader.readline());self.assertEqual(event['event'],'staged')
                self.assertEqual((root/'save/save_009.xml.gz').read_bytes(),data)
                time.sleep(1.25)
                parent.sendall(b'{"command":"claim"}\n')
                payload,control,flags,_=parent.recvmsg(1,socket.CMSG_SPACE(array.array('i').itemsize))
            fds=[]
            for level,kind,value in control:
                if (level,kind)==(socket.SOL_SOCKET,socket.SCM_RIGHTS):
                    a=array.array('i');a.frombytes(value[:len(value)-(len(value)%a.itemsize)]);fds.extend(a)
            try:
                self.assertEqual(payload,b'F');self.assertEqual(flags & socket.MSG_CTRUNC,0);self.assertEqual(len(fds),1)
                self.assertEqual(proc.wait(timeout=4),0)
                with socket.socket(fileno=fds.pop()) as transferred: transferred.sendall(b'from-handoff\n')
            finally:
                for fd in fds: os.close(fd)
                parent.close()
            thread.join(4);self.assertFalse(thread.is_alive());self.assertFalse(errors)
            self.assertGreaterEqual(len(keep),1);self.assertEqual(keep,list(range(1,len(keep)+1)))
            self.assertEqual(len(claimed),1);self.assertEqual(claimed[0].marker,marker)

if __name__=='__main__': unittest.main()
