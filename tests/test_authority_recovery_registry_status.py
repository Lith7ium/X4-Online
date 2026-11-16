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
    def test_first_save_binds_then_compares_full_mapping(self):
        initial=('bootstrap','a'*32,2);actual=('ready','a'*32,2,'f'*64)
        self.assertEqual(status.checkpoint_status(initial,actual),actual)
        for bad in (('uninitialized',),('ready','b'*32,2,'f'*64),('ready','a'*32,1,'f'*64)):
            with self.assertRaises(ValueError):status.checkpoint_status(initial,bad)
        with self.assertRaises(ValueError):status.checkpoint_status(actual,('ready','a'*32,2,'e'*64))
    def test_enrollment_receipt_unique_and_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'log';n='a'*32;e='b'*32
            line='[X4LAN] AUTH_RECOVERY_ENROLL '+n+'|'+e+'|2\n'
            p.write_text(line);self.assertEqual(status.enrollment_receipt(p,n,e,3),2)
            for bad in (line+line,line.replace('|2','|4'),line.replace(e,'c'*32)):
                p.write_text(bad)
                with self.assertRaises(ValueError):status.enrollment_receipt(p,n,e,3)
    def test_enrollment_owner(self):
        subprocess.run(['luajit','tests/authority_recovery_registry_enroll.lua'],cwd=ROOT,check=True,capture_output=True)
    def test_lua_owner(self):
        subprocess.run(['luajit','tests/authority_recovery_registry_status.lua'],cwd=ROOT,check=True,capture_output=True)
    def test_install_enrollment_exclusive_routing_and_status_transition(self):
        with tempfile.TemporaryDirectory() as d:
            case=Path(d)/'case';profile=Path(d)/'45841'
            ui=case/'extensions/x4_lan_lab/ui';md=ui.parent/'md';ui.mkdir(parents=True);md.mkdir();profile.mkdir()
            def fake_base(case,port,lease,epoch,marker_required):
                (ui/'authority_world_bridge_probe.lua').write_text((ROOT/'tools/dev/authority_world_bridge_probe.lua').read_text())
            with patch.object(recovery.bridge_install,'install_probe',side_effect=fake_base):
                recovery.install_probe(case,profile,1234,'a'*32,'b'*32)
            options={'epoch':'d'*32,'nonce':'e'*32,'limit':3,'save_path':str(profile/'save')}
            files=status.install(case,'c'*32,('uninitialized',),enroll=options)
            self.assertEqual(len(files),6)
            owner=(ui/'authority_world_bridge_probe.lua').read_text()
            self.assertIn("if registry_enroller and registry_enroller:state()~='done'",owner)
            self.assertIn('registry_status:expect_bootstrap(epoch,count)',owner)
            self.assertLess(owner.index('registry_enroller:state()'),owner.index('RECOVERY_READY|'))
            for file in [*files,ui/'authority_world_bridge_probe.lua']:
                if file.suffix=='.lua':subprocess.run(['luajit','-b',str(file),'/dev/null'],check=True,capture_output=True)
    def test_reject_enroll_into_existing_registry(self):
        with self.assertRaises(ValueError):
            status.install('/not/used','a'*32,('ready','b'*32,1,'c'*64),
                enroll={'epoch':'d'*32,'nonce':'e'*32,'limit':3,'save_path':'/tmp/45841/save'})

    def test_invalid_hooks_do_not_modify_overlay_for_status_or_enrollment(self):
        hooks = (
            ('ui.xml', '    <file name="ui/authority_world_bridge_probe.lua" />\n'),
            ('ui/authority_world_bridge_probe.lua', 'local activated=false\n'),
            ('ui/authority_world_bridge_probe.lua', ' if not activated then\n'),
            ('ui/authority_world_bridge_probe.lua',
             "    AddUITriggeredEvent('X4AuthorityCheckpointMarker','Store',{marker=marker})\n"),
        )
        for enrollment in (False, True):
            for relative, hook in hooks:
                for replacement in ('', hook + hook):
                    with self.subTest(enrollment=enrollment, hook=hook, duplicated=bool(replacement)), \
                         tempfile.TemporaryDirectory() as directory:
                        case = Path(directory)/'case'
                        profile = Path(directory)/'45841'
                        ui = case/'extensions/x4_lan_lab/ui'
                        lab = ui.parent
                        ui.mkdir(parents=True)
                        (lab/'md').mkdir()
                        profile.mkdir()
                        def fake_base(case, port, lease, epoch, marker_required):
                            (ui/'authority_world_bridge_probe.lua').write_text(
                                (ROOT/'tools/dev/authority_world_bridge_probe.lua').read_text())
                        with patch.object(recovery.bridge_install, 'install_probe', side_effect=fake_base):
                            recovery.install_probe(case, profile, 1234, 'a'*32, 'b'*32)
                        target = lab/relative
                        original = target.read_text()
                        self.assertEqual(original.count(hook), 1)
                        target.write_text(original.replace(hook, replacement))
                        before = {path.relative_to(lab): path.read_bytes()
                                  for path in lab.rglob('*') if path.is_file()}
                        options = {'epoch':'d'*32, 'nonce':'e'*32, 'limit':3,
                                   'save_path':str(profile/'save')} if enrollment else None
                        with self.assertRaises(ValueError):
                            status.install(case, 'c'*32, ('uninitialized',), enroll=options)
                        after = {path.relative_to(lab): path.read_bytes()
                                 for path in lab.rglob('*') if path.is_file()}
                        self.assertEqual(after, before)
                        target.write_text(original)
                        installed = status.install(case, 'c'*32, ('uninitialized',), enroll=options)
                        self.assertEqual(len(installed), 6 if enrollment else 2)

    def test_duplicate_generated_enrollment_hooks_fail_before_writes(self):
        duplicate_hooks = (
            '    <file name="ui/recovery_registry_status.lua" />\n',
            'local registry_status=nil\n',
            "register=function(f)return RegisterEvent('X4AuthorityShipRegistry.Correlated',f)~=false end,",
            ' if not registry_status:ready() then return end\n',
        )
        for hook in duplicate_hooks:
            with self.subTest(hook=hook), tempfile.TemporaryDirectory() as directory:
                case = Path(directory)/'case'
                profile = Path(directory)/'45841'
                ui = case/'extensions/x4_lan_lab/ui'
                lab = ui.parent
                ui.mkdir(parents=True)
                (lab/'md').mkdir()
                profile.mkdir()
                def fake_base(case, port, lease, epoch, marker_required):
                    (ui/'authority_world_bridge_probe.lua').write_text(
                        (ROOT/'tools/dev/authority_world_bridge_probe.lua').read_text())
                with patch.object(recovery.bridge_install, 'install_probe', side_effect=fake_base):
                    recovery.install_probe(case, profile, 1234, 'a'*32, 'b'*32)
                target = lab/'ui.xml' if hook.startswith('    <file') else ui/'authority_world_bridge_probe.lua'
                target.write_text(target.read_text() + hook)
                before = {path.relative_to(lab): path.read_bytes()
                          for path in lab.rglob('*') if path.is_file()}
                options = {'epoch':'d'*32, 'nonce':'e'*32, 'limit':3,
                           'save_path':str(profile/'save')}
                with self.assertRaises(ValueError):
                    status.install(case, 'c'*32, ('uninitialized',), enroll=options)
                after = {path.relative_to(lab): path.read_bytes()
                         for path in lab.rglob('*') if path.is_file()}
                self.assertEqual(after, before)

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
