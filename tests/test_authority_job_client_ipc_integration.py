"""Actual Python IPC and Lua owner/client over local UDP, with simulated MD/FFI."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from authority.experimental_participant_job_ipc import ExperimentalParticipantJobIPC
LEASE,ATTEMPT,EPOCH,GEN=('a'*32,'b'*32,'c'*32,'d'*32)
class Integration(unittest.TestCase):
    def test_real_lua_owner_and_python_bridge_wait_for_simulated_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=Path(tmp)/'net.so'
            subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','src/native/net.c','-ldl','-o',str(lib)],cwd=ROOT,check=True,capture_output=True)
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));self.addCleanup(sock.close)
            env=dict(os.environ,TEST_NET_LIB=str(lib),TEST_NET_PORT=str(sock.getsockname()[1]))
            proc=subprocess.Popen(['luajit','tests/authority_job_client_ipc_fake_x4.lua'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            def stop():
                if proc.poll() is None:proc.terminate()
                proc.communicate(timeout=3)
            self.addCleanup(stop)
            bridge=ExperimentalParticipantJobIPC(sock,enabled=True,lease=LEASE,attempt=ATTEMPT,epoch=EPOCH,generation=GEN,
                guard=lambda:proc.poll() is None,validate_peer=lambda peer:peer[0]=='127.0.0.1',timeout=2)
            self.assertTrue(bridge.wait_ready())
            event={'epoch':EPOCH,'generation':GEN,'sequence':1,'index':3,'descriptor':{'macro':'ship_a',
                'faction':'argon','sector_macro':'sector_a','x':1,'y':2,'z':3}}
            start=time.monotonic();self.assertTrue(bridge(event));self.assertGreaterEqual(time.monotonic()-start,.18)
            self.assertIsNone(proc.poll());bridge.close()
