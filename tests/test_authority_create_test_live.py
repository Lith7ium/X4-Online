"""Protocol-level checks for the disposable test driver; no game is started."""
import importlib.util
from pathlib import Path
import time

import tempfile
import subprocess
import shutil
import unittest
from unittest.mock import patch

PATH=Path(__file__).resolve().parents[1]/'tools/dev/authority_create_test_live.py'
spec=importlib.util.spec_from_file_location('authority_create_test_live',PATH)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class FakeSocket:
    def __init__(self,lease,changed=False):
        self.lease=lease;self.changed=changed
        self.address={'server':('127.0.0.1',1),'client':('127.0.0.1',2)}
        self.queue=[self.packet('server','HELLO'),self.packet('client','HELLO')]
    def packet(self,role,row):
        return (f'RESULT|{self.lease}|{role}|{row}'.encode(),self.address[role])
    def sendto(self,data,addr):
        parts=data.decode().split('|');op=parts[2]
        if op=='CREATE':
            assert parts[3:]==['ship_arg_s_fighter_01_a_macro','cluster_01','argon','7183','-400','100000','500']
        role=next(k for k,v in self.address.items() if v==addr)
        rows={'SPAWN':'SPAWN|1|42|5|6|cluster_01|ship_arg_s_fighter_01_a_macro|argon|7183|-400|100000|500',
              'CREATE':'CREATE|1|84|7|8|cluster_01',
              'REPLAY':f'REPLAY|1|{85 if self.changed else 84}|7|8|cluster_01',
              'CONFLICT':'CONFLICT|8','STATUS':'FAULTED','AFTER':'AFTER_CONFLICT|8'}
        self.queue.append(self.packet(role,rows[op]))
    def recvfrom(self,_): return self.queue.pop(0)
    def close(self): pass


class ProbeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT is not installed')
    def test_lua_conversion_and_invalid_macro(self):
        root=PATH.parents[2]
        driver=root/'tests/lua/authority_create_probe_conversion.lua'
        for variant in ([],['invalid-macro']):
            with self.subTest(variant=variant):
                result=subprocess.run(['luajit',str(driver),*variant],cwd=root,
                                      capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT is not installed')
    def test_lua_client_descriptor_and_sector_mismatch(self):
        root=PATH.parents[2]
        driver=root/'tests/lua/authority_create_probe_client_descriptor.lua'
        for variant in ([],['sector-mismatch']):
            with self.subTest(variant=variant):
                result=subprocess.run(['luajit',str(driver),*variant],cwd=root,
                                      capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_replay_requires_same_identity(self):
        for changed in (False,True):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                exp=module.Experiment();exp.sock.close();exp.sock=FakeSocket(exp.lease,changed)
                result={};root=Path(directory)
                kwargs=dict(server_proc='server',server_started=1,server_identity='server',
                            client_proc='client',client_started=2,client_identity='client',game=root,
                            out=root,deadline=time.monotonic()+3,result=result)
                try:
                    with patch.object(module.base.client,'game_identity',side_effect=lambda proc,*_:proc):
                        if changed:
                            with self.assertRaisesRegex(ValueError,'replay'):exp.on_ready(**kwargs)
                            self.assertNotIn('creation_test',result)
                        else:
                            exp.on_ready(**kwargs)
                            self.assertTrue(result['creation_test']['replay_same_local_reference'])
                            self.assertTrue(result['creation_test']['fixture_descriptor_forwarded_over_loopback'])
                            self.assertEqual(result['creation_test']['client_matching_faction_macro_after'],8)
                finally: exp.close()

if __name__=='__main__': unittest.main()
