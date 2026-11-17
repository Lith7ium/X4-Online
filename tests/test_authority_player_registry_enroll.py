"""Offline contracts for the opt-in historical registry fixture owner."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class PlayerRegistryEnrollTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_serial_legacy_enroll_resolve_and_failure_fences(self):
        subprocess.run(['luajit', 'tests/authority_player_registry_enroll.lua'],
                       cwd=ROOT, check=True, timeout=10, capture_output=True)

    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'), 'LuaJIT and C compiler required')
    def test_x4_adapter_with_synthetic_ffi(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / 'fake-x4.so'
            subprocess.run(['cc', '-shared', '-fPIC', 'tests/lua/authority_player_seat_fake_x4.c',
                            'tests/lua/authority_player_registry_fake_x4.c', '-o', str(library)],
                           cwd=ROOT, check=True, timeout=10, capture_output=True)
            subprocess.run(['luajit', 'tests/authority_player_registry_enroll_x4.lua', str(library)],
                           cwd=ROOT, check=True, timeout=10, capture_output=True)

    def test_fixture_read_is_separate_and_has_no_registry_writes(self):
        root = ET.parse(ROOT / 'tools/dev/authority_player_registry_read.xml').getroot()
        self.assertEqual(root.get('name'), 'X4AuthorityPlayerRegistryRead')
        self.assertEqual(root.find('.//event_ui_triggered').get('control'), "'Read'")
        for action in root.iter('set_value'):
            self.assertTrue(action.get('name', '').startswith('$'))
        self.assertFalse(root.findall('.//create_ship'))
        self.assertFalse(root.findall('.//teleport_player'))
