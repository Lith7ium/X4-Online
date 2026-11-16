"""Offline synthetic checks; no X4 or networking."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]

class PairCreate(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_async_callback_states(self):
        subprocess.run(['luajit','tests/authority_sector_pair_create.lua'],cwd=ROOT,check=True,capture_output=True,timeout=5)
    @unittest.skipUnless(shutil.which("cc") and shutil.which("luajit"),"C compiler and LuaJIT required")
    def test_fake_native_ffi_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            so=Path(tmp)/"fake.so"
            subprocess.run(["cc","-shared","-fPIC","tests/lua/authority_sector_pair_create_fake_x4.c","-o",str(so)],cwd=ROOT,check=True,capture_output=True,timeout=10)
            subprocess.run(["luajit","tests/authority_sector_pair_create_fake_x4.lua",str(so)],cwd=ROOT,check=True,capture_output=True,timeout=5)
    def test_md_guard_is_read_only_and_binds_descriptor(self):
        root=ET.parse(ROOT/'tools/dev/authority_sector_pair_create_inspect.xml').getroot()
        self.assertEqual({n.tag for n in root.iter()},{'mdscript','cues','cue','conditions','event_ui_triggered','actions','set_value','do_if','do_else','raise_lua_event'})
        guard=' '.join(n.attrib.get('value','') for n in root.iter('do_if'))
        for field in ('macro','sector','owner','seed','x','y','z'):
            self.assertIn('$v.$'+field,guard)
        for key in ('$ship.sector == $sector','State.$pending == false','State.$byship.{$ship} == 3','State.$receipts.{3} == $ship'):
            self.assertIn(key,guard)
    def test_x4_adapter_does_not_install_update_or_socket(self):
        data=(ROOT/'tools/dev/authority_sector_pair_create_x4.lua').read_text()
        for s in ('SetScript(', 'package.loadlib', 'net:send', 'net:receive'):
            self.assertNotIn(s,data)
        for s in ('C.GetObjectPositionInSector(a)','X4LAN_RESOLVE_STRING.parse_hex','C.IsGamePaused()'):
            self.assertIn(s,data)
