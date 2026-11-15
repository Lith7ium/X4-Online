"""Isolated jobs case synthetic tests; no native X4 execution."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('jobs_case',ROOT/'tools/dev/authority_sector_jobs_case_live.py')
jobs=importlib.util.module_from_spec(spec);spec.loader.exec_module(jobs)

class JobsCaseTests(unittest.TestCase):
    def test_simulated_control_treatment_and_fail_closed_cases(self):
        for mode in ('control','treatment','disabled','dispatch','wrong_id','wrong_id_sample','sector_change',
                     'actor_mismatch','actor_mismatch_sample','highsame','highmismatch','pause_loss',
                     'pause_loss_running','duplicate','timeout','timeout_running','initial_game_mismatch'):
            with self.subTest(mode=mode):
                subprocess.run(['luajit','tests/authority_sector_jobs_case.lua',mode],cwd=ROOT,check=True,capture_output=True)
    def test_correlated_xml_emits_actor_and_only_treatment_sets_jobs(self):
        root=ET.parse(ROOT/'tools/dev/authority_sector_jobs_correlated.xml').getroot()
        setters=root.findall('.//set_space_jobs_allowed');self.assertEqual(len(setters),1)
        branches=[n for n in root.findall('.//do_if') if n.get('value')=="$mode == 'treatment'"]
        self.assertEqual(len(branches),1);self.assertIs(branches[0].find('set_space_jobs_allowed'),setters[0])
        for event,actor in (('Began','$ship'),('Sampled','State.$ship')):
            node=root.find('.//raise_lua_event[@name="\'X4AuthoritySectorJobsCorrelated.'+event+'\'"]')
            self.assertIn('$request_id',node.get('param'));self.assertIn(actor,node.get('param'))
        self.assertFalse(root.findall('.//create_order'));self.assertFalse(root.findall('.//create_ship'))
    def test_private_overlay_uses_single_update_owner_and_paused_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
            ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
            for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',
                      lab/'content.xml',profile/'content.xml',profile/'config.xml'): p.write_text('test')
            t=dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,
                checkpoint_id=jobs.base.archive.CHECKPOINT_ID,sha256=jobs.base.archive.SHA256,attempt_id='b'*32,slot='save_009')
            protected=jobs.install(case,profile,t,2,'control','c'*32,5.)
            owner=(ui/'authority_download_load_probe.lua').read_text();self.assertEqual(owner.count("SetScript('onUpdate'"),1)
            self.assertIn("if state=='done' then X4LAN_JOBS_CASE_READY();return end",owner)
            read=(ui/'authority_sector_read_probe.lua').read_text();self.assertIn("if state~='done' or failed",read)
            self.assertIn(' guard()\n if first[1]',read)
            self.assertIn(md/'authority_sector_jobs_correlated.xml',protected)
            self.assertIn(ui/'authority_sector_jobs_case.lua',protected)
    def test_validator_requires_complete_correlated_six_sample_window(self):
        original=jobs.base_check
        jobs.base_check=lambda *a,**k:{'reported_order_id':'Patrol','reported_pilot':'present','reported_order_state':'started','reported_game_time':3.}
        try:
            prefix=['[X4LAN] AUTH_JOBS_CASE BEGAN mode=control order=Patrol game=3']
            rows=prefix+['[X4LAN] AUTH_JOBS_CASE SAMPLE n=%d pilot=same order=Patrol order_state=started real=%d game_before=%d game_after=%d x=1 y=2 z=3'%(n,n,3+n,3+n) for n in range(1,7)]
            rows+=['[X4LAN] AUTH_JOBS_CASE DONE mode=control samples=6 game=9']
            def raw(lines): return ('\n'.join(lines)+'\n').encode()
            report=jobs.validate(raw(rows),{},2,'control',5)
            self.assertTrue(report['final_pause_checked']);self.assertEqual(len(report['samples']),6)
            self.assertIsNone(jobs.validate(raw(rows[:-1]),{},2,'control',5,partial=True))
            for bad in (rows+[rows[-1]],rows[:2]+[rows[2].replace('n=2','n=1')]+rows[3:],
                        rows[:1]+[rows[1].replace('game_after=4','game_after=2')]+rows[2:],
                        [rows[0].replace('game=3','game=2')]+rows[1:],
                        [rows[0].replace('mode=control','mode=treatment')]+rows[1:]):
                with self.subTest(bad=bad),self.assertRaises(ValueError): jobs.validate(raw(bad),{},2,'control',5)
            with self.assertRaises(ValueError): jobs.validate(raw(rows),{},2,'control',7)
        finally: jobs.base_check=original

if __name__=='__main__': unittest.main()
