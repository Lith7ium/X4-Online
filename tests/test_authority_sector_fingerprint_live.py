"""Synthetic, isolated checks; never starts X4."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_sector_fingerprint_live as subject

EXPECTED={1:dict(index=1,ship_code='LBT-457',ship_macro='ship_x',sector_code='VHB-132',sector_macro='sector_x'),
          2:dict(index=2,ship_code='ABC-309',ship_macro='ship_y',sector_code='CWZ-318',sector_macro='sector_y')}


def evidence():
    rows=[]
    for i in range(4):
        slot=i%2+1;r=EXPECTED[slot]
        rows.append(subject.TAG+f"ROW slot={slot} n={i//2+1} ship_code={r['ship_code']} ship_macro={r['ship_macro']} sector_code={r['sector_code']} sector_macro={r['sector_macro']} game=3")
    rows.append(subject.TAG+'DONE samples=4 game=3')
    return rows


def raw(rows): return ('\n'.join(rows)+'\n').encode()


class SectorFingerprintTests(unittest.TestCase):
    def test_lua_correlations_and_local_guards(self):
        for mode in ('ok','disabled','dispatch','wrong_id','wrong_epoch','actor_change','sector_change',
                     'initial_mismatch','bad_hex','pause_loss','duplicate','timeout','missing_sector','changed_attributes'):
            with self.subTest(mode=mode):
                subprocess.run(['luajit','tests/authority_sector_fingerprint.lua',mode],cwd=ROOT,check=True,capture_output=True)

    def test_xml_is_read_only_and_maps_slots_to_references(self):
        root=ET.parse(ROOT/'tools/dev/authority_sector_fingerprint.xml').getroot()
        for mutation in ('set_object_velocity','create_ship','create_order','set_object_position','signal_objects'):
            self.assertFalse(root.findall('.//'+mutation))
        self.assertEqual(len(root.findall('.//cue')),1)
        text=ET.tostring(root,encoding='unicode')
        for part in ('$request_id','$epoch','$index','$ship','$sector','$ship.idcode',
                     '$ship.macro.id','$sector.idcode','$sector.macro.id',
                     '$ship.sector == $sector','not $ship.dock.exists','not $ship.isinternallystored'):
            self.assertIn(part,text)

    def test_install_reuses_update_owner_and_protects_new_files(self):
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
            self.assertIn('X4LAN_SECTOR_FINGERPRINT_READY()',owner)
            self.assertIn(md/'authority_sector_fingerprint.xml',protected)
            self.assertIn(ui/'authority_sector_fingerprint.lua',protected)

    def test_evidence_rejects_mismatch_and_unavailable(self):
        with patch.object(subject,'base_check',return_value={'reported_game_time':3.}):
            rows=evidence();result=subject.validate(raw(rows),{},2,EXPECTED)
            self.assertEqual(len(result['fingerprint_rows']),4)
            self.assertFalse(result['runtime_binding_proven'])
            self.assertIsNone(subject.validate(raw(rows[:-1]),{},2,EXPECTED,partial=True))
            for bad in (rows+[rows[-1]],rows[:2]+[rows[2].replace('LBT-457','ZZZ-999')]+rows[3:],
                        rows[:1]+[rows[1].replace('CWZ-318','null')]+rows[2:],
                        rows[:2]+[rows[2].replace('game=3','game=4')]+rows[3:],
                        [subject.TAG+'ERROR refused']+rows):
                with self.assertRaises(ValueError): subject.validate(raw(bad),{},2,EXPECTED)

    def test_profiles_are_strictly_sequential_and_fail_closed(self):
        origin={'checkpoint_id':'checkpoint-x','sha256':'a'*64,'registry_epoch':'b'*32}
        fingerprints={'slots':[EXPECTED[1],EXPECTED[2]]}
        for scenario in ('ok','first_failed','first_cleanup_unconfirmed','second_failed'):
            with self.subTest(scenario=scenario),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);out=root/'out';source=root/'archive'/'checkpoints';source.mkdir(parents=True)
                calls=[]
                def run_arm(args):
                    calls.append(args.out.name);args.out.mkdir()
                    if scenario=='first_cleanup_unconfirmed' and len(calls)==1: return {'success':True,'owned_processes_remaining':[123]}
                    ok=not (scenario=='first_failed' or (scenario=='second_failed' and len(calls)==2))
                    return {'success':ok,'owned_processes_remaining':[]}
                args=SimpleNamespace(out=out,store=source,slot=2)
                with patch.object(subject.base.snapshot,'output_path',side_effect=lambda p:Path(p)), \
                     patch.object(subject.base.base,'local_directory',return_value=source), \
                     patch.object(subject.base.archive,'DEFAULT_STORE',source), \
                     patch.object(subject.base.archive,'_path_fingerprints',return_value={'stable':True}), \
                     patch.object(subject.base.archive,'verify',return_value=origin), \
                     patch.object(subject,'CheckpointStore') as store, \
                     patch.object(subject.saved,'verify',return_value=fingerprints), \
                     patch.object(subject.base,'run',side_effect=run_arm):
                    store.return_value.latest_confirmed.return_value=object()
                    result=subject.run(args)
                self.assertEqual(calls,['profile-1','profile-2'] if scenario in ('ok','second_failed') else ['profile-1'])
                self.assertEqual(result['success'],scenario=='ok')

if __name__=='__main__': unittest.main()
