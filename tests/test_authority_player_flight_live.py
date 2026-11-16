"""Offline integration contracts only; never starts X4."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tests.test_authority_player_control_live as control_test
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('flight_live',ROOT/'tools/dev/authority_player_flight_live.py')
live=importlib.util.module_from_spec(spec);spec.loader.exec_module(live)

class FlightLiveTest(unittest.TestCase):
    def setUp(self):
        self.control=control_test.PlayerControlLiveTests();self.control.setUp()
        self.ticket=self.control.ticket
        self.control_lines=[]
        for step in self.control.controlled:
            if step=='DISPATCH': self.control_lines.extend([live.control.MD_TAG+'ACTION_BEGIN',live.control.MD_TAG+'ACTION_RETURNED'])
            self.control_lines.append(live.control.TAG+step)
        self.baseline=self.control.baseline+self.control_lines
        self.steps=['ARMED 0 3','RESUME_INTENT','RESUME_RETURNED','RUNNING 1 4']+[
            'SAMPLE '+str(i)+' '+str(i)+' '+str(i)+' '+str(i+3)+' '+str(i+3)+' 1 2 3 4 5 6' for i in (1,2,3)]+['DONE','FENCED']
    def raw(self,steps):return ('\n'.join(self.baseline+[live.TAG+s for s in steps])+'\n').encode()
    def test_completed_and_invalid_evidence(self):
        for i in range(len(self.steps)):
            self.assertIsNone(live.validate(self.raw(self.steps[:i]),self.ticket,2,partial=True))
        result=live.validate(self.raw(self.steps),self.ticket,2)
        self.assertTrue(result['flight_observation_completed']);self.assertFalse(result['flight_proven']);self.assertFalse(result['input_proven'])
        for steps in (self.steps+['DONE'], self.steps[:-2]+['FENCED','DONE'], self.steps+['FENCED'], self.steps[:3]+['RUNNING 1 3'], self.steps[:4]+[self.steps[4].replace('SAMPLE 1','SAMPLE 2')],
                      self.steps[:4]+[self.steps[4].replace(' 1 2 3 4 5 6',' nan 2 3 4 5 6')], self.steps+['ERROR FAULT']):
            with self.subTest(steps=steps),self.assertRaises(ValueError): live.validate(self.raw(steps),self.ticket,2,partial=True)
    def test_install_protects_only_private_hooks(self):
        with tempfile.TemporaryDirectory() as temp:
            case=Path(temp)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
            ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
            for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',lab/'content.xml',profile/'content.xml',profile/'config.xml'): p.write_text('test')
            protected=live.install(case,profile,self.ticket,2,90)
            self.assertTrue({md/live.MD,*(ui/n for n in live.UI)}.issubset(protected))
            owner=(ui/'authority_download_load_probe.lua').read_text()
            self.assertEqual(owner.count("SetScript('onUpdate'"),1);self.assertIn('X4LAN_PLAYER_FLIGHT_LIVE_TICK()',owner)
            self.assertIn('not handed',(ui/'authority_player_control_live_owner.lua').read_text())
    def test_inconclusive_control_never_claims_flight(self):
        lines=self.control.baseline+[live.control.TAG+s for s in ('START','INCONCLUSIVE','DONE')]
        lines += [live.TAG+'INCONCLUSIVE',live.TAG+'DONE']
        result=live.validate(('\n'.join(lines)+'\n').encode(),self.ticket,2)
        self.assertEqual(result['flight_observation_outcome'],'inconclusive')
        self.assertFalse(result['flight_observation_completed']);self.assertFalse(result['local_control_proven'])
    def test_archive_change_removes_result_and_restores_hooks(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);store=root/'source'/'checkpoints';store.mkdir(parents=True);out=root/'output'
            args=SimpleNamespace(slot=2,timeout=120,out=out,store=store);holder={}
            old=(live.base.install,live.base.check_log_bytes,live.base.fault_log,live.base.base.readonly_save_command,live.base.result_finalizer)
            def fake_run(_):
                holder['result']={'success':True,'outcome':'controlled','diagnostic_completed':True,
                                  'local_control_proven':True,'flight_observation_completed':True,'samples':[{}]}
                live.base.result_finalizer(holder['result']);return holder['result']
            with patch.object(live.base.snapshot,'output_path',return_value=out), \
                 patch.object(live.base.base,'local_directory',return_value=store), \
                 patch.object(live.base.archive,'_path_fingerprints',side_effect=[{'a':1},{'a':2}]), \
                 patch.object(live.base,'run',side_effect=fake_run):
                with self.assertRaises(ValueError):live.run(args)
            self.assertNotIn('outcome',holder['result']);self.assertNotIn('samples',holder['result'])
            self.assertNotIn('flight_observation_completed',holder['result']);self.assertFalse(holder['result']['local_control_proven'])
            self.assertEqual(old,(live.base.install,live.base.check_log_bytes,live.base.fault_log,live.base.base.readonly_save_command,live.base.result_finalizer))
    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_owner_timing_and_reentrancy(self):
        for mode in ('normal','inconclusive','slow','pause_lost','reentrant','slow_sample','pause_sample','slow_done','pause_done'):
            subprocess.run(['luajit','tests/authority_player_flight_live_owner.lua',mode],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_owner_drives_actual_observer(self):
        subprocess.run(['luajit','tests/authority_player_flight_live_real_observer.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
if __name__=='__main__':unittest.main()
