import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_recovery_registry_status as status
import authority_recovery_registry_witness as witness
import authority_recovery_bridge_live as recovery
import authority_recovered_loopback_server as owner

class WitnessTests(unittest.TestCase):
    def test_lua_sequence_and_fail_closed(self):
        subprocess.run(['luajit','tests/authority_recovery_registry_witness.lua'],cwd=ROOT,check=True,capture_output=True)
    def test_private_install_and_script_parses(self):
        with tempfile.TemporaryDirectory() as d:
            case=Path(d)/'case';profile=Path(d)/'45841';profile.mkdir()
            lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md';ui.mkdir(parents=True);md.mkdir()
            def fake_base(case,port,lease,epoch,marker_required):
                (ui/'authority_world_bridge_probe.lua').write_text((ROOT/'tools/dev/authority_world_bridge_probe.lua').read_text())
            with patch.object(recovery.bridge_install,'install_probe',side_effect=fake_base):
                recovery.install_probe(case,profile,1234,'a'*32,'b'*32)
            status.install(case,'a'*32,('ready','b'*32,2,'c'*64))
            files=witness.install(case,'d'*32,'b'*32,2,'create')
            self.assertEqual(len(files),2)
            ET.parse(md/'authority_registry_witness.xml')
            for file in [ui/'authority_world_bridge_probe.lua',ui/'recovery_registry_witness.lua']:
                subprocess.run(['luajit','-b',str(file),'/dev/null'],check=True,capture_output=True)
            probe=(ui/'authority_world_bridge_probe.lua').read_text()
            self.assertIn("phase='create'",probe)
            with self.assertRaises(ValueError):witness.install(case,'d'*32,'b'*32,2,'create')
    def test_generated_probe_allows_resume_only_for_join(self):
        for allow,mode in ((True,'join'),(True,'pause_before_done'),(False,'standalone'),(False,'standalone_create')):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                case=Path(d)/'case';profile=Path(d)/'45841';profile.mkdir()
                lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md';ui.mkdir(parents=True);md.mkdir()
                def fake_base(case,port,lease,epoch,marker_required):
                    (ui/'authority_world_bridge_probe.lua').write_text((ROOT/'tools/dev/authority_world_bridge_probe.lua').read_text())
                with patch.object(recovery.bridge_install,'install_probe',side_effect=fake_base):
                    recovery.install_probe(case,profile,1234,'a'*32,'b'*32)
                status.install(case,'a'*32,('ready','b'*32,2,'c'*64))
                phase='create' if mode=='standalone_create' else 'verify'
                witness.install(case,'d'*32,'b'*32,2,phase,allow_resume=allow)
                subprocess.run(['luajit','tests/authority_recovery_witness_probe.lua',
                    str(ui/'authority_world_bridge_probe.lua'),mode],cwd=ROOT,check=True,capture_output=True)

    def test_resume_option_rejects_create_or_non_boolean(self):
        with tempfile.TemporaryDirectory() as d:
            for phase,value in (('create',True),('verify',1)):
                with self.subTest(phase=phase,value=value), self.assertRaises(ValueError):
                    witness.install(Path(d),'d'*32,'b'*32,2,phase,allow_resume=value)

    def test_receipt_unique_bound_and_complete(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'log';n='a'*32;e='b'*32
            line=f'[X4LAN] AUTH_RECOVERY_WITNESS {n}|{e}|2|verify|sealed\n'
            path.write_text(line);self.assertTrue(witness.matches_log(path,n,e,2,'verify'))
            for data in (line+line,line[:-1],line.replace('|2|','|3|'),line.replace('|verify|','|create|')):
                path.write_text(data)
                with self.assertRaises(ValueError):witness.matches_log(path,n,e,2,'verify')
    def test_final_closed_log_refuses_late_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'log';n='a'*32;e='b'*32
            line=f'[X4LAN] AUTH_RECOVERY_WITNESS {n}|{e}|2|create|sealed\n'
            path.write_text(line)
            self.assertTrue(witness.matches_log(path,n,e,2,'create'))
            with path.open('a') as stream:stream.write(line)
            with self.assertRaises(ValueError):owner.verify_final_witness(path,n,e,2,'create')
    def test_final_closed_log_refuses_late_bridge_error(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'log';n='a'*32;e='b'*32
            path.write_text(f'[X4LAN] AUTH_RECOVERY_WITNESS {n}|{e}|2|create|sealed\n')
            self.assertTrue(witness.matches_log(path,n,e,2,'create'))
            with path.open('a') as stream:stream.write('[X4LAN] AUTH_WORLD_BRIDGE ERROR failed callback\n')
            with self.assertRaises(ValueError):owner.verify_final_witness(path,n,e,2,'create')
    def test_live_watcher_detects_split_error_and_file_replacement(self):
        for tag in witness.ErrorWatch.TAGS:
            with self.subTest(tag=tag), tempfile.TemporaryDirectory() as d:
                path=Path(d)/'log'; watch=witness.ErrorWatch(path); watch.poll()
                cut=len(tag)//2;path.write_bytes(b'noise\n'+tag[:cut]);watch.poll()
                with path.open('ab') as stream:stream.write(tag[cut:]+b'failed\n')
                with self.assertRaises(ValueError):watch.poll()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'log';path.write_text('ok\n');watch=witness.ErrorWatch(path);watch.poll()
            path.unlink();path.write_text('new content\n')
            with self.assertRaises(ValueError):watch.poll()
