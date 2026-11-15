"""Read-only calibration probe structure and synthetic Lua control flow."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]

class SeatProbeTest(unittest.TestCase):
    def test_md_only_reads_cues_and_requires_live_context_and_valid_post(self):
        root=ET.parse(ROOT/'tools/dev/authority_player_seat_calibration.xml').getroot()
        self.assertEqual({node.tag for node in root.iter()},
            {'mdscript','cues','cue','conditions','event_ui_triggered','actions','set_value',
             'do_if','do_elseif','do_else','raise_lua_event'})
        self.assertTrue(all(node.get('name','').startswith('$') for node in root.iter('set_value')))
        expressions=' '.join(node.get('value','') for node in root.iter('do_if'))
        for term in ('not md.X4AuthorityPlayerSectorFixture.State.$faulted',
                     'not md.X4AuthorityShipRegistry.State.$faulted','$ship.sector == $sector',
                     '$ship != player.occupiedship','$post and $post.component'):
            self.assertIn(term,expressions)
        values=[node.get('exact') for node in root.iter('set_value')]
        self.assertIn('$ship.controlpostslot.{controlpost.aipilot}',values)
        self.assertIn('$post.component.slotactor.{$post}',values)
        rows=list(root.iter('raise_lua_event'))
        self.assertEqual(sum(node.get('name')=="'X4AuthorityPlayerSeatCalibration.Result'" for node in rows),1)
        self.assertIn('$v.$request_id',rows[0].get('param',''))

    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_correlated_positive_control_and_failure_paths(self):
        subprocess.run(['luajit','tests/authority_player_seat_calibration.lua'],cwd=ROOT,
                       check=True,capture_output=True,text=True,timeout=5)

    @unittest.skipUnless(shutil.which('cc') and shutil.which('luajit'),'C compiler and LuaJIT required')
    def test_x4_binding_distinguishes_nil_from_getter_error(self):
        with tempfile.TemporaryDirectory() as directory:
            library=Path(directory)/'fake-x4.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_player_seat_fake_x4.c',
                            '-o',str(library)],cwd=ROOT,check=True,capture_output=True,timeout=10)
            subprocess.run(['luajit','tests/authority_player_seat_fake_x4.lua',str(library)],cwd=ROOT,
                           check=True,capture_output=True,text=True,timeout=5)

if __name__=='__main__':unittest.main()
