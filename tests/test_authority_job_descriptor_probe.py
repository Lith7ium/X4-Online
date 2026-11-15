"""Read-only job descriptor diagnostics with synthetic callbacks, no X4."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]

class JobDescriptorTest(unittest.TestCase):
    def test_md_is_read_only_and_emits_one_correlated_result(self):
        root=ET.parse(ROOT/'tools/dev/authority_job_descriptor_probe.xml').getroot()
        self.assertEqual({n.tag for n in root.iter()}, {'mdscript','cues','cue','conditions','event_ui_triggered',
            'actions','set_value','do_if','do_else','raise_lua_event'})
        self.assertTrue(all(n.get('name','').startswith('$') for n in root.iter('set_value')))
        guards=' '.join(n.get('value','') for n in root.iter('do_if'))
        for term in ('not md.X4AuthorityShipRegistry.State.$faulted',
                     '@md.X4AuthorityShipRegistry.State.$byship.{$ship} == $index',
                     '@$ship.sector.isclass.sector'):
            self.assertIn(term,guards)
        result=root.find('.//raise_lua_event').get('param')
        for term in ('$v.$request_id','$v.$epoch','$index','$ship.macro.id','$ship.owner.id','$ship.sector.macro.id'):
            self.assertIn(term,result)

    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_lua_correlates_original_actor_and_fails_closed(self):
        subprocess.run(['luajit','tests/authority_job_descriptor_probe.lua'],cwd=ROOT,
                       check=True,capture_output=True,text=True,timeout=5)

    @unittest.skipUnless(shutil.which('cc') and shutil.which('luajit'),'C compiler and LuaJIT required')
    def test_fake_x4_exact_large_actor_and_sector_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            library=Path(directory)/'fake-x4.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_job_descriptor_fake_x4.c',
                            '-o',str(library)],cwd=ROOT,check=True,capture_output=True,timeout=10)
            subprocess.run(['luajit','tests/authority_job_descriptor_fake_x4.lua',str(library)],cwd=ROOT,
                           check=True,capture_output=True,text=True,timeout=5)

if __name__=='__main__': unittest.main()
