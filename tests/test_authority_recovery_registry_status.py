import gzip
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev'),str(ROOT/'tests')]
import authority_recovery_registry_status as status
import authority_recovery_bridge_live as recovery
from authority.checkpoints import Checkpoint
from test_authority_registry_save_evidence import xml, EPOCH

class StatusTests(unittest.TestCase):
    def checkpoint(self,text):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup)
        path=Path(d.name)/'save.xml.gz';data=gzip.compress(text.encode());path.write_bytes(data)
        return Checkpoint('checkpoint-'+'a'*32,path,hashlib.sha256(data).hexdigest(),len(data))
    def test_dynamic_saved_status(self):
        result=status.saved_status(self.checkpoint(xml()))
        self.assertEqual(result[:3],('ready',EPOCH,2));self.assertEqual(len(result[3]),64)
        self.assertEqual(status.saved_status(self.checkpoint('<savegame/>')),('uninitialized',))
    def test_swapped_valid_bijection_has_different_fingerprint(self):
        original=xml();changed=original.replace('value="[0x1]"','value="[0xTEMP]"').replace('value="[0x2]"','value="[0x1]"').replace('value="[0xTEMP]"','value="[0x2]"')
        self.assertNotEqual(status.saved_status(self.checkpoint(original)),status.saved_status(self.checkpoint(changed)))
    def test_missing_component_and_ambiguous_registry_fail(self):
        with self.assertRaises(ValueError):status.saved_status(self.checkpoint(xml().replace('class="ship_l"','class="station"')))
        with self.assertRaises(ValueError):status.saved_status(self.checkpoint(xml().replace('</md>','<script name="X4AuthorityShipRegistry"/></md>')))
    def test_native_waiting_state_without_children_is_uninitialized(self):
        saved='''<savegame><md><script id="309" name="X4AuthorityShipRegistry">
        <cue id="694584" name="Enroll" state="waiting"/>
        <cue id="694585" name="Resolve" state="waiting"/>
        <cue id="694582" name="State" state="waiting"/>
        <cue id="694583" name="Status" state="waiting"/>
        </script></md></savegame>'''
        self.assertEqual(status.saved_status(self.checkpoint(saved)),('uninitialized',))
        for altered in (
            saved.replace('name="State" state="waiting"','name="State" state="complete"'),
            saved.replace('<cue id="694582" name="State" state="waiting"/>','<cue id="694582" name="State" state="waiting"><vars/></cue>'),
            saved.replace('<cue id="694582" name="State" state="waiting"/>','<cue id="694582" name="State" state="waiting"><unexpected/></cue>'),
            saved.replace('<cue id="694582" name="State" state="waiting"/>','<cue id="694582" name="State" state="waiting">unexpected</cue>'),
            saved.replace('<cue id="694582" name="State" state="waiting"/>','<cue id="694582" name="State" state="waiting"/><cue id="2" name="State" state="waiting"/>'),
            saved.replace('<cue id="694582" name="State" state="waiting"/>',''),
            saved.replace('name="State" state="waiting"','name="State" state="waiting" unexpected="1"'),
        ):
            with self.subTest(altered=altered),self.assertRaises(ValueError):status.saved_status(self.checkpoint(altered))
    def test_receipt_must_match_unique_context(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'log';n='a'*32;m='b'*32
            line='[X4LAN] AUTH_RECOVERY_REGISTRY '+n+'|'+m+'|uninitialized\n'
            p.write_text(line);self.assertTrue(status.matches_log(p,n,m,('uninitialized',)))
            p.write_text(line+line)
            with self.assertRaises(ValueError):status.matches_log(p,n,m,('uninitialized',))
    def test_lua_owner(self):
        subprocess.run(['luajit','tests/authority_recovery_registry_status.lua'],cwd=ROOT,check=True,capture_output=True)
    def test_installs_into_real_recovery_owner_hooks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);case=root/'case';profile=root/'45841'
            ui=case/'extensions/x4_lan_lab/ui';md=ui.parent/'md';ui.mkdir(parents=True);md.mkdir()
            profile.mkdir()
            def fake_base(case,port,lease,epoch,marker_required):
                (ui/'authority_world_bridge_probe.lua').write_text((ROOT/'tools/dev/authority_world_bridge_probe.lua').read_text())
            with patch.object(recovery.bridge_install,'install_probe',side_effect=fake_base):
                recovery.install_probe(case,profile,1234,'a'*32,'b'*32)
            status.install(case,'c'*32,('uninitialized',))
            owner=(ui/'authority_world_bridge_probe.lua').read_text()
            self.assertIn('assert(registry_status:begin(marker))',owner)
            self.assertLess(owner.index('if not X4LAN_AUTHORITY_RECOVERY_READY()'),owner.index('if not registry_status then'))
            self.assertLess(owner.index('if not registry_status:ready()'),owner.index('RECOVERY_READY|'))
            for file in (ui/'recovery_registry_status.lua',ui/'authority_world_bridge_probe.lua'):
                subprocess.run(['luajit','-b',str(file),'/dev/null'],check=True,capture_output=True)

if __name__=='__main__':unittest.main()
