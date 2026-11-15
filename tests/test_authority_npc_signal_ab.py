"""Offline tests of the disposable NPC signal diagnostic; no X4 process."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_npc_signal_ab_live as subject


def evidence(mode='control'):
    tag=subject.TAG
    rows=[tag+f'BEGAN mode={mode} order=Patrol order_state=started game=3']
    t=3
    for phase,count,interval in (('before',3,1),('during',3,1),('after',5,5),('tail',5,5)):
        if phase=='during': rows.append(tag+f'APPLIED game={t}')
        if phase=='after': rows.append(tag+f'RELEASED game={t}')
        if phase=='tail': rows.append(tag+f"DECISION mode={mode} outcome={'noop' if mode=='control' else 'sent'} order=Patrol order_state=started game={t}")
        for n in range(1,count+1):
            t+=interval
            rows.append(tag+f'SAMPLE phase={phase} n={n} pilot=same order=Patrol order_state=started real={t} game_before={t} game_after={t} x={t} y=0 z=0')
    rows.append(tag+f'DONE mode={mode} before=3 during=3 after=5 tail=5 game={t}')
    return rows


def raw(rows): return ('\n'.join(rows)+'\n').encode()


class SignalABTests(unittest.TestCase):
    def test_lua_both_arms_and_faults(self):
        for mode,arm in [('ok','control'),('ok','treatment'),('order_changed','control'),
                         ('wrong_mode','treatment'),('order_persist','treatment'),('dispatch','control'),('wrong_id','control'),
                         ('pause_loss','control'),('actor_change','control'),('refuse','control'),
                         ('duplicate','control'),('timeout','control')]:
            with self.subTest(mode=mode,arm=arm):
                subprocess.run(['luajit','tests/authority_npc_signal_ab.lua',mode,arm],cwd=ROOT,check=True,capture_output=True)

    def test_md_signal_fenced_and_single_set_release(self):
        root=ET.parse(ROOT/'tools/dev/authority_npc_signal_ab.xml').getroot()
        signal=root.findall('.//signal_objects');self.assertEqual(len(signal),1)
        self.assertEqual(signal[0].attrib,{'object':'State.$pilot','param':"'patch_reset_moveto'"})
        decision=root.find('.//cue[@name="Decision"]/actions/do_if')
        for part in ('$valid',"State.$phase == 'after'"):
            self.assertIn(part,decision.get('value'))
        treatment=decision.find('./do_if')
        self.assertEqual(treatment.get('value'),"State.$mode == 'treatment'")
        signal_guard=treatment.find('./do_if').get('value')
        self.assertIn('State.$ship.order.id == State.$orderid',signal_guard)
        self.assertIn('State.$ship.order.state == State.$orderstate',signal_guard)
        self.assertIsNotNone(decision.find("./set_value[@name='State.$phase'][@exact=\"'tail'\"]"))
        setters=root.findall('.//set_object_velocity');self.assertEqual(len(setters),2)
        self.assertEqual(setters[0].get('constantvel'),'true')
        self.assertEqual(setters[0].find('linear').attrib,{'x':'0m / 1s','y':'0m / 1s','z':'0m / 1s'})
        self.assertEqual(setters[1].get('constantvel'),'false');self.assertEqual(len(setters[1]),0)
        guard=root.find('.//library[@name="Guard"]/actions/set_value').get('exact')
        for part in ('State.$ship.pilot == State.$pilot','State.$ship.sector == State.$sector',
                     'State.$ship.parent == State.$parent','not State.$ship.dock.exists',
                     'not State.$ship.isinternallystored'):
            self.assertIn(part,guard)
        self.assertFalse(root.findall('.//create_ship'));self.assertFalse(root.findall('.//create_order'))

    def test_install_wires_one_owner_and_arm(self):
        with tempfile.TemporaryDirectory() as temp:
            case=Path(temp)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
            ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
            for path in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',
                         lab/'content.xml',profile/'content.xml',profile/'config.xml'): path.write_text('test')
            ticket=dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,
                        checkpoint_id=subject.base.archive.CHECKPOINT_ID,sha256=subject.base.archive.SHA256,
                        attempt_id='b'*32,slot='save_009')
            protected=subject.install(case,profile,ticket,2,'c'*32,'treatment')
            self.assertIn('authority_npc_signal_mode="treatment"',(ui/'config.lua').read_text())
            owner=(ui/'authority_download_load_probe.lua').read_text()
            self.assertEqual(owner.count("SetScript('onUpdate'"),1)
            self.assertIn('X4LAN_NPC_SIGNAL_AB_READY()',owner)
            self.assertIn(md/'authority_npc_signal_ab.xml',protected)
            self.assertNotIn(md/'authority_sector_jobs_correlated.xml',protected)

    def test_evidence_checks_timing_order_and_arm(self):
        old=subject.jobs.base_check
        subject.jobs.base_check=lambda *a,**k:{'reported_order_id':'Patrol','reported_pilot':'present',
            'reported_order_state':'started','reported_game_time':3.}
        try:
            for arm in ('control','treatment'):
                rows=evidence(arm);result=subject.validate(raw(rows),{},2,arm)
                self.assertEqual(len(result['samples']),16)
                self.assertEqual(result['signal_dispatch_requested'],arm=='treatment')
                self.assertFalse(result['signal_handler_execution_proven'])
                self.assertFalse(result['complete_state_restored_proven'])
                changed=[r.replace('order_state=started real=14','order_state=other real=14') for r in rows]
                self.assertTrue(subject.validate(raw(changed),{},2,arm)['observed_order_changed'])
                if arm=='treatment':
                    skipped=[r.replace('outcome=sent','outcome=skipped_order') for r in changed]
                    result=subject.validate(raw(skipped),{},2,arm)
                    self.assertEqual(result['decision_outcome'],'skipped_order')
                    self.assertFalse(result['signal_dispatch_requested'])
                self.assertIsNone(subject.validate(raw(rows[:-1]),{},2,arm,partial=True))
                for bad in (rows+[rows[-1]],rows[:9]+rows[10:],
                    [r.replace('DECISION mode='+arm,'DECISION mode=wrong') for r in rows],
                    [r.replace('order_state=started real=4','order_state=other real=4') for r in rows],
                    [r.replace('game_before=14 game_after=14','game_before=13 game_after=13') for r in rows]):
                    with self.assertRaises(ValueError): subject.validate(raw(bad),{},2,arm)
        finally: subject.jobs.base_check=old

if __name__=='__main__': unittest.main()
