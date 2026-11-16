"""Real participant TCP -> UDP -> Lua owner/client, with simulated MD/FFI."""
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from authority.experimental_participant_job_ipc import ExperimentalParticipantJobIPC
from authority.experimental_tcp_job_delivery import job_digest
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient

LEASE,ATTEMPT,EPOCH,GEN=('a'*32,'b'*32,'c'*32,'d'*32)

class Controller:
    def pause(self, handles): return True
    def resume(self, handles): return True

class TCPLuaIntegration(unittest.TestCase):
    def test_receipt_waits_for_real_lua_owner_and_simulated_md_ffi(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=Path(tmp)/'net.so'
            subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','src/native/net.c','-ldl','-o',str(lib)],
                           cwd=ROOT,check=True,capture_output=True)
            udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0))
            self.addCleanup(udp.close)
            env=dict(os.environ,TEST_NET_LIB=str(lib),TEST_NET_PORT=str(udp.getsockname()[1]))
            proc=subprocess.Popen(['luajit','tests/authority_job_client_ipc_fake_x4.lua'],cwd=ROOT,env=env,
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            def stop():
                if proc.poll() is None:proc.terminate()
                proc.communicate(timeout=3)
            self.addCleanup(stop)
            bridge=ExperimentalParticipantJobIPC(udp,enabled=True,lease=LEASE,attempt=ATTEMPT,epoch=EPOCH,generation=GEN,
                guard=lambda:proc.poll() is None,validate_peer=lambda peer:peer[0]=='127.0.0.1',timeout=2)
            self.assertTrue(bridge.wait_ready())
            listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);self.addCleanup(listener.close)
            host=socket.create_connection(listener.getsockname());client,_=listener.accept()
            self.addCleanup(host.close);self.addCleanup(client.close);host.settimeout(3)
            event={'epoch':EPOCH,'generation':GEN,'sequence':1,'index':3,'descriptor':{'macro':'ship_a',
                   'faction':'argon','sector_macro':'sector_a','x':1,'y':2,'z':3}}
            command={'version':1,'kind':'job_delivery','connection_handle':1,'request_id':1,
                     'session_epoch':EPOCH,'incarnation':'f'*32,'event':event}
            result=[];errors=[]
            def remote():
                try:
                    host.sendall(json.dumps(command).encode()+b'\n')
                    result.append(('early',bool(select.select([host],[],[],.1)[0])))
                    result.append(('receipt',json.loads(host.recv(4096))))
                except BaseException as e:errors.append(e)
            thread=threading.Thread(target=remote);thread.start();self.addCleanup(thread.join,3)
            participant=ExperimentalTCPParticipantClient(client,Controller(),enabled=True,epoch=EPOCH,handle=1,
                                                          timeout=3,apply_job=bridge)
            deadline=time.monotonic()+3
            while time.monotonic()<deadline and not participant.poll(.05):pass
            thread.join(3);self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
            self.assertEqual(result[0],('early',False))
            self.assertEqual(result[1][1]['kind'],'job_receipt')
            self.assertEqual(result[1][1]['event_sha256'],job_digest(event))
            self.assertIsNone(proc.poll());participant.close();bridge.close()

if __name__=='__main__':unittest.main()
