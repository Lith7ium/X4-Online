"""Structural checks and fake-callback tests, not an X4 semantic test."""
from pathlib import Path
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

class SectorReadProbe(unittest.TestCase):
    def test_xml_is_only_local_read_and_emits_guarded_fields(self):
        root = ET.parse(ROOT / 'tools/dev/authority_sector_read_guard.xml').getroot()
        allowed = {'mdscript', 'cues', 'cue', 'conditions', 'event_ui_triggered', 'actions',
                   'set_value', 'do_if', 'do_elseif', 'do_else', 'raise_lua_event'}
        self.assertFalse({e.tag for e in root.iter()} - allowed)
        for node in root.iter('set_value'):
            self.assertTrue(node.get('name', '').startswith('$'))
        guards = ' '.join(node.get('value', '') for node in root.iter('do_if'))
        for part in ('$v.$slot == 1', '$v.$slot == 2', '$ship.sector == $sector',
                     'State.$ships.{$index} == $ship', 'State.$byship.{$ship} == $index'):
            self.assertIn(part, guards)
        for name in ('Pilot', 'OrderId', 'OrderState', 'Actor', 'Sector', 'Verified', 'Refused'):
            self.assertTrue(root.findall('.//raise_lua_event[@name="\'X4AuthoritySectorReadGuard.' + name + '\'"]'))

    def test_synthetic_callbacks(self):
        for mode in ('slot1', 'slot2', 'pause', 'reorder', 'unsafe', 'unsafe-input', 'rounded',
                     'highsame', 'highchanged', 'dispatch', 'disabled', 'clock', 'late', 'changed'):
            with self.subTest(mode=mode):
                subprocess.run(['luajit', 'tests/authority_sector_read_probe.lua', mode], cwd=ROOT, check=True,
                               capture_output=True, text=True)

if __name__ == '__main__':
    unittest.main()
