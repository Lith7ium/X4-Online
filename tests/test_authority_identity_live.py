import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('identity_live',ROOT/'tools/dev/authority_identity_live.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class IdentityFixtureTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_lua_helper(self):
        subprocess.run(['luajit',str(ROOT/'tests/authority_identity_peer.lua')],cwd=ROOT,check=True)

    def test_observations_are_distinct_and_ordered(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'log'
            prefix='[X4LAN] AUTH_IDENTITY save '
            def line(i,identity,name):
                return prefix+f'ACTOR {i} id={identity} name=Authority identity {name} macro=ship_arg_s_fighter_01_a_macro\n'
            p.write_text(line(1,123,'alpha 7181')+line(2,124,'beta 7182')+prefix+'READY\n')
            self.assertEqual(len(m.observations(p,'save')),2)
            p.write_text(line(1,123,'alpha 7181')+line(2,123,'beta 7182')+prefix+'READY\n')
            with self.assertRaises(ValueError): m.observations(p,'save')

if __name__=='__main__': unittest.main()
