"""Synthetic string payload and private overlay checks, without launching X4."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('resolve_string_live',ROOT/'tools/dev/authority_registry_resolve_string_live.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class ResolveStringTest(unittest.TestCase):
    def test_md_only_string_result_and_read_only_registry(self):
        root=ET.parse(ROOT/'tools/dev/authority_registry_resolve_string.xml').getroot()
        for action in root.iter('set_value'): self.assertTrue(action.attrib['name'].startswith('$'))
        replies=list(root.iter('raise_lua_event'));self.assertEqual(len(replies),3)
        for reply in replies:
            self.assertEqual(reply.attrib['name'],"'X4AuthorityRegistryResolveString.Result'")
            self.assertTrue(reply.attrib['param'].startswith("'%s|%s|%s|"))
            self.assertNotIn('table[',reply.attrib['param'])

    def test_overlay_is_separate_and_contains_no_table_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';profile=case/'home/45841'
            ui.mkdir(parents=True);(lab/'md').mkdir();(profile/'save').mkdir(parents=True)
            def install_bridge(*_):
                (ui/'config.lua').write_text('X4LAN_CONFIG = {}\n')
                (ui/'authority_world_bridge_probe.lua').write_text(' if not started and now-loaded_at>=3 then\n')
                (lab/'ui.xml').write_text('    <file name="ui/authority_world_bridge_probe.lua" />\n')
            with patch.object(M.base.world_bridge,'install_probe',side_effect=install_bridge):
                M.install(case,profile,port=1000,lease='a'*32,epoch='b'*32,id1='c'*32,id2='d'*32)
            self.assertTrue((lab/'md/authority_registry_resolve_string.xml').exists())
            self.assertFalse((lab/'md/authority_registry_resolve_v2.xml').exists())
            self.assertIn('X4LAN_RESOLVE_STRING_NATIVE_READY',(ui/'authority_world_bridge_probe.lua').read_text())

    def test_log_requires_both_string_responses(self):
        p='[X4LAN] AUTH_RESOLVE_STRING '
        good=(p+'SHAPE stage=ok type=string actor_format=hex actor_length=18\n'+p+'ACTOR_MATCH\n'
              +p+'SHAPE stage=unavailable type=string actor_format=hex actor_length=1\n'+p+'UNAVAILABLE\n'+p+'DONE\n')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'log';path.write_text(good);self.assertTrue(M.check_log(path)['actor_match_observed'])
            for bad in (good+p+'DONE\n',good.replace('actor_format=hex','actor_format=other',1)):
                path.write_text(bad)
                with self.assertRaises(ValueError): M.check_log(path)

    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_exact_uint64_and_correlated_responses(self):
        subprocess.run(['luajit','tests/authority_registry_resolve_string.lua'],cwd=ROOT,
                       capture_output=True,text=True,check=True,timeout=5)

    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_synthetic_native_callback_driver(self):
        for mode in ('ok','number-safe','high-cdata','unsafe-number','actor-mismatch','no-prefix','bad-id','pause-loss','dispatch-false'):
            with self.subTest(mode=mode):
                subprocess.run(['luajit','tests/authority_registry_resolve_string_native.lua',mode],cwd=ROOT,
                               capture_output=True,text=True,check=True,timeout=5)


if __name__=='__main__': unittest.main()
