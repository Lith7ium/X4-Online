"""Structural MD and synthetic Lua contract; not an X4 or MD interpreter test."""
from pathlib import Path
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


class ResolveV2Test(unittest.TestCase):
    def test_md_response_and_registry_read_only_structure(self):
        root=ET.parse(ROOT/'tools/dev/authority_registry_resolve_v2.xml').getroot()
        self.assertEqual({v.tag for v in root.iter()}, {'mdscript','cues','cue','conditions',
                         'event_ui_triggered','actions','set_value','do_if','do_else','raise_lua_event'})
        for action in root.iter('set_value'):
            self.assertTrue(action.attrib['name'].startswith('$'))
        guards=' and '.join(x.attrib['value'] for x in root.iter('do_if'))
        for fragment in ('not md.X4AuthorityShipRegistry.State.$faulted',
                         '$v.$epoch == md.X4AuthorityShipRegistry.State.$epoch',
                         '@$ship.isoperational','$ship.isclass.ship',
                         '@md.X4AuthorityShipRegistry.State.$byship.{$ship} == $index'):
            self.assertIn(fragment,guards)
        replies=list(root.iter('raise_lua_event'))
        self.assertEqual(len(replies),3)
        for reply in replies:
            self.assertEqual(reply.attrib['name'],"'X4AuthorityRegistryResolveV2.Result'")
            for name in ('$request_id=','$epoch=','$index=','$actor=','$status='):
                self.assertIn(name,reply.attrib['param'])

    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_synthetic_driver(self):
        subprocess.run(['luajit','tests/authority_registry_resolve_v2.lua'],cwd=ROOT,
                       capture_output=True,text=True,check=True,timeout=5)


if __name__=='__main__': unittest.main()
