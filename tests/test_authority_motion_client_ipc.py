"""Local actual UDP/Lua owner/binding, with fake X4 ABI and simulated MD."""
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
class ClientMotionIPC(unittest.TestCase):
    def test_socket_owner_is_exclusive(self):
        subprocess.run(['luajit','tests/authority_motion_client_owner.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
    def test_bound_only_after_correlated_md_and_ffi(self):
        with tempfile.TemporaryDirectory() as tmp:
            net=Path(tmp)/'net.so';abi=Path(tmp)/'fake.so'
            subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC','src/native/net.c','-ldl','-o',str(net)],cwd=ROOT,check=True,capture_output=True)
            subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/replica_motion_binding_abi.c','-o',str(abi)],cwd=ROOT,check=True,capture_output=True)
            for mode in ('good','rate','bad_md','despawn','overlap','stale_clock','partial_rate','bad_coord','bad_audit'):
                with self.subTest(mode=mode):
                    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));sock.settimeout(2)
                    env=dict(os.environ,LD_PRELOAD=str(abi),TEST_NET_LIB=str(net),TEST_NET_PORT=str(sock.getsockname()[1]))
                    if mode=='bad_md':env['TEST_BAD_MD']='1'
                    if mode=='despawn':env['TEST_DESPAWN']='1'
                    if mode=='bad_audit':env['TEST_BAD_AUDIT']='1'
                    if mode=='rate':env['TEST_EXPECT_RATE']='1'
                    proc=subprocess.Popen(['luajit','tests/authority_motion_client_ipc_fake_x4.lua'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                    try:
                        ready,peer=sock.recvfrom(768);self.assertEqual(ready,('R|'+'a'*32+'|'+'b'*32+'|READY|'+'c'*32+'|'+'d'*32).encode())
                        req='|'.join(['M','a'*32,'b'*32,'BIND','f'*32,'c'*32,'d'*32,'42','1','sector_a','1'*64,'10','1','2','3',*(['4','5','6'] if mode=='rate' else ['-','-','-'])]).encode()
                        if mode=='partial_rate':
                            parts=req.split(b'|');parts[15]=b'4';req=b'|'.join(parts)
                        if mode=='bad_coord':
                            parts=req.split(b'|');parts[12]=b'10000001';req=b'|'.join(parts)
                        started=time.monotonic();sock.sendto(req,peer)
                        if mode=='overlap':
                            time.sleep(.03);sock.sendto(req,peer)
                        self.assertFalse(select.select([sock],[],[],.1)[0],'premature receipt')
                        if mode in ('good','rate','stale_clock'):
                            data,_=sock.recvfrom(768);self.assertGreaterEqual(time.monotonic()-started,.18)
                            expected=b'|'.join(req.split(b'|')[:11]).replace(b'M|',b'R|',1).replace(b'|BIND|',b'|BOUND|',1)
                            self.assertEqual(data,expected)
                            stale=req.replace(b'f'*32,b'9'*32)
                            if mode=='stale_clock':
                                parts=stale.split(b'|');parts[8]=b'2';stale=b'|'.join(parts)
                            sock.sendto(stale,peer);proc.wait(timeout=2)
                            self.assertFalse(select.select([sock],[],[],0)[0],'stale sample accepted')
                        else:
                            proc.wait(timeout=2);self.assertFalse(select.select([sock],[],[],0)[0])
                    finally:
                        if proc.poll() is None:proc.terminate()
                        _,err=proc.communicate(timeout=3);sock.close()
                        if mode in ('good','rate','stale_clock'):self.assertFalse(err,err.decode(errors='replace'))
