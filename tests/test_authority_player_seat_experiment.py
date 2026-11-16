"""Disposable fixture/seat owner is default-off and fails closed on event errors."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]

class Experiment(unittest.TestCase):
    def test_preflight_is_read_only_and_fences_fresh_fixture(self):
        root=ET.parse(ROOT/'tools/dev/authority_player_seat_experiment.xml').getroot()
        self.assertEqual({e.tag for e in root.iter()}, {'mdscript','cues','cue','conditions',
            'event_ui_triggered','actions','set_value','do_if','do_else','raise_lua_event'})
        self.assertTrue(all(e.get('name','').startswith('$') for e in root.iter('set_value')))
        cond=root.find('.//do_if').get('value')
        for term in ("player.module == 'custom_creative'",'not md.X4AuthorityPlayerSectorFixture.State.$epoch?',
                     'not md.X4AuthorityPlayerSectorFixture.State.$pending?',
                     'not md.X4AuthorityPlayerSectorFixture.State.$faulted?',
                     'not md.X4AuthorityShipRegistry.State.$faulted','$s1 != $s2',
                     'md.X4AuthorityShipRegistry.State.$byship.{$a2} == 2'):
            self.assertIn(term,cond)

    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_serialized_guarded_events(self):
        subprocess.run(['luajit','tests/authority_player_seat_experiment.lua'],cwd=ROOT,
                       check=True,capture_output=True,text=True,timeout=5)

    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'),'LuaJIT and C compiler required')
    def test_real_adapter_over_fake_x4_abi(self):
        with tempfile.TemporaryDirectory() as d:
            library=Path(d)/'fake-x4.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_player_seat_fake_x4.c',
                            'tests/lua/authority_player_seat_experiment_time.c','-o',str(library)],
                           cwd=ROOT,check=True,capture_output=True,timeout=10)
            subprocess.run(['luajit','tests/authority_player_seat_experiment_x4.lua',str(library)],
                           cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
