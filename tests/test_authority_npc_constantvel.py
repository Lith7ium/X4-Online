"""Synthetic constant-velocity experiment checks; never starts X4."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_npc_constantvel_live as subject


class ConstantVelocityTests(unittest.TestCase):
    def test_lua_sequence_and_fail_closed_conditions(self):
        for mode in ('ok','order_changed','dispatch','wrong_id','pause_loss','actor_change','refuse','duplicate','timeout'):
            with self.subTest(mode=mode):
                subprocess.run(['luajit','tests/authority_npc_constantvel.lua',mode],cwd=ROOT,check=True,capture_output=True)

    def test_md_has_one_zero_set_and_release_without_velocity_children(self):
        root=ET.parse(ROOT/'tools/dev/authority_npc_constantvel.xml').getroot()
        setters=root.findall('.//set_object_velocity');self.assertEqual(len(setters),2)
        self.assertEqual(setters[0].get('constantvel'),'true')
        self.assertEqual(setters[0].find('linear').attrib,{'value':'vector.[0m, 0m, 0m]'})
        self.assertEqual(setters[1].get('constantvel'),'false');self.assertEqual(len(setters[1]),0)
        self.assertFalse(root.findall('.//create_ship'));self.assertFalse(root.findall('.//create_order'))
        guard=root.find('.//library[@name="Guard"]/actions/set_value').get('exact')
        for part in ('State.$ship.pilot == State.$pilot','State.$ship.sector == State.$sector',
                     'not State.$ship.dock.exists','not State.$ship.isinternallystored'):
            self.assertIn(part,guard)

    def test_private_install_reuses_one_update_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            case=Path(temp)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
            ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
            for path in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',
                         lab/'content.xml',profile/'content.xml',profile/'config.xml'): path.write_text('test')
            ticket=dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,
                        checkpoint_id=subject.base.archive.CHECKPOINT_ID,sha256=subject.base.archive.SHA256,
                        attempt_id='b'*32,slot='save_009')
            protected=subject.install(case,profile,ticket,2,'c'*32)
            owner=(ui/'authority_download_load_probe.lua').read_text()
            self.assertEqual(owner.count("SetScript('onUpdate'"),1)
            self.assertIn('X4LAN_NPC_CONSTANTVEL_READY()',owner)
            self.assertIn(md/'authority_npc_constantvel.xml',protected)
            self.assertNotIn(md/'authority_sector_jobs_correlated.xml',protected)

    def test_evidence_requires_all_phases_and_ordered_receipts(self):
        old=subject.jobs.base_check
        subject.jobs.base_check=lambda *a,**k:{'reported_order_id':'Patrol','reported_pilot':'present',
                                               'reported_order_state':'started','reported_game_time':3.}
        try:
            rows=[subject.TAG+'BEGAN order=Patrol game=3']
            for phase,base_time in (('before',4),('during',8),('after',12)):
                if phase=='during': rows.append(subject.TAG+'APPLIED game=7')
                if phase=='after': rows.append(subject.TAG+'RELEASED game=11')
                for n in range(1,4):
                    t=base_time+n-1
                    rows.append(subject.TAG+f'SAMPLE phase={phase} n={n} pilot=same order=Patrol order_state=started real={t} game_before={t} game_after={t} x={t} y=0 z=0')
            rows.append(subject.TAG+'DONE before=3 during=3 after=3 game=15')
            raw=lambda lines: ('\n'.join(lines)+'\n').encode()
            result=subject.validate(raw(rows),{},2)
            self.assertEqual(len(result['samples']),9);self.assertFalse(result['complete_state_restored_proven'])
            self.assertIsNone(subject.validate(raw(rows[:-1]),{},2,partial=True))
            for bad in (rows[:4]+rows[5:],rows+[rows[-1]],rows[:4]+[rows[4].replace('APPLIED','RELEASED')]+rows[5:],
                        rows[:2]+[rows[2].replace('x=5','x=nan')]+rows[3:]):
                with self.assertRaises(ValueError): subject.validate(raw(bad),{},2)
        finally: subject.jobs.base_check=old


if __name__=='__main__': unittest.main()
