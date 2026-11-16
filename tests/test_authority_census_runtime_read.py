"""Synthetic runtime reader checks; never starts X4."""
from pathlib import Path
import hashlib
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_census_runtime_read_live as subject


class CensusRuntimeTests(unittest.TestCase):
    def test_save_specific_scripts_are_exact_and_mismatch_is_rejected(self):
        registry=subject.archive.saved_state_script('authority_ship_registry.xml')
        self.assertEqual(hashlib.sha256(registry.read_bytes()).hexdigest(),
                         '8b7c9887c9c1476e45fe84a60243547d96e09b11d4c40fabd151930af517e939')
        self.assertNotEqual(registry.read_bytes(),(ROOT/'tools/dev/authority_ship_registry.xml').read_bytes())
        with self.assertRaises(ValueError):subject.archive.saved_state_script('../other.xml')
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source';store=source/'checkpoints';store.mkdir(parents=True)
            origin=source/'server/case';md=origin/'extensions/x4_lan_lab/md';md.mkdir(parents=True)
            content=origin/'home/.config/EgoSoft/X4/45841/content.xml';content.parent.mkdir(parents=True)
            profile=Path(temp)/'profile';profile.mkdir();content.write_text('same');(profile/'content.xml').write_text('same')
            names=('authority_checkpoint_marker.xml','authority_ship_registry.xml','authority_identity_fixture.xml')
            for name in names:(md/name).write_bytes(subject.archive.saved_state_script(name).read_bytes())
            subject.origin_scripts(store,profile)
            for name in names:
                path=md/name;old=path.read_bytes();path.write_bytes(old+b' changed')
                with self.assertRaisesRegex(ValueError,'saved-state scripts differ'):subject.origin_scripts(store,profile)
                path.write_bytes(old)
            (profile/'content.xml').write_text('different')
            with self.assertRaisesRegex(ValueError,'extension lists differ'):subject.origin_scripts(store,profile)

    def test_lua_reads_over_103_and_fails_closed(self):
        for mode in ('ok','wrong_id','pause_loss','duplicate','timeout'):
            with self.subTest(mode=mode):
                subprocess.run(['luajit','tests/authority_census_runtime_read.lua',mode],cwd=ROOT,check=True,capture_output=True)

    def test_md_only_reads_and_correlates(self):
        root=ET.parse(ROOT/'tools/dev/authority_census_runtime_read.xml').getroot()
        self.assertFalse(root.findall('.//create_ship'))
        self.assertFalse(root.findall('.//set_object_velocity'))
        for action in root.findall('.//set_value'):
            self.assertTrue(action.get('name','').startswith('$'))
        events=root.findall('.//raise_lua_event[@name="\'X4AuthorityCensusRuntimeRead.Result\'"]')
        self.assertEqual(len(events),5)
        self.assertTrue(all('$request_id' in e.get('param') and '$epoch' in e.get('param') for e in events))

    def test_private_install_has_single_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            case=Path(temp)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
            ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
            for path in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',
                         lab/'content.xml',profile/'content.xml',profile/'config.xml'): path.write_text('test')
            ticket=dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,
                        checkpoint_id=subject.archive.CHECKPOINT_ID,sha256=subject.archive.SHA256,
                        attempt_id='b'*32,slot='save_009')
            protected=subject.install(case,profile,ticket,1,'c'*32,105,600)
            self.assertIn(md/'authority_census_runtime_read.xml',protected)
            self.assertEqual((md/'authority_ship_registry.xml').read_bytes(),
                             subject.archive.saved_state_script('authority_ship_registry.xml').read_bytes())
            owner=(ui/'authority_download_load_probe.lua').read_text()
            self.assertEqual(owner.count("SetScript('onUpdate'"),1)
            self.assertIn('if not X4LAN_CENSUS_RUNTIME_READY() then return end',owner)
            self.assertNotIn('SetScript(', (ui/'authority_census_runtime_read.lua').read_text())

    def test_output_is_disjoint_from_whole_source_experiment(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';store=source/'checkpoints';store.mkdir(parents=True)
            for out in (source,source/'new-output',root):
                with self.assertRaisesRegex(ValueError,'separate'): subject.ensure_separate(out,store)
            subject.ensure_separate(root/'other',store)

    def test_log_validation_checks_positions_counts_and_order(self):
        ticket={k:('x' if k not in ('connection_handle','baseline_id','load_generation') else 1)
                for k in subject.base.load.FIELDS}
        fields='|'.join(str(ticket[k]) for k in subject.base.load.FIELDS)
        rows=[subject.base.load.TAG.decode()+'load_requested|'+fields,
              '[X4LAN] AUTH_MARKER load INSPECTED '+subject.archive.MARKER]
        for i in range(1,106):
            rows.append(subject.TAG+f'ROW index={i} status=ok local_sector=0x20 x={i} y=2 z=3')
        rows += [subject.TAG+'DONE requested=105 ok=105 unavailable=0 no_sector=0 docked_or_stored=0 local_invalid=0 sectors=1 game=5',
                 subject.base.load.TAG.decode()+'pause_observed|'+fields]
        raw=lambda r: ('\n'.join(r)+'\n').encode()
        result=subject.validate(raw(rows),ticket,1,limit=105)
        self.assertEqual((result['position_reads'],result['local_sectors']),(105,1))
        self.assertTrue(result['position_observation_conclusive'])
        self.assertIsNone(subject.validate(raw(rows[:-1]),ticket,1,limit=105,partial=True))
        for bad in (rows[:5]+[rows[5].replace('index=4','index=5')]+rows[6:],
                    rows[:5]+[rows[5].replace('y=2','y=nan')]+rows[6:],
                    rows[:-2]+[rows[-2].replace('ok=105','ok=104')]+rows[-1:]):
            with self.assertRaises(ValueError): subject.validate(raw(bad),ticket,1,limit=105)

    def test_failure_categories_are_explicit_and_do_not_count_as_positions(self):
        ticket={k:('x' if k not in ('connection_handle','baseline_id','load_generation') else 1)
                for k in subject.base.load.FIELDS}
        fields='|'.join(str(ticket[k]) for k in subject.base.load.FIELDS)
        rows=[subject.base.load.TAG.decode()+'load_requested|'+fields,
              '[X4LAN] AUTH_MARKER load INSPECTED '+subject.archive.MARKER]
        for i,status in enumerate(('unavailable','no_sector','docked_or_stored','local_invalid'),1):
            rows.append(subject.TAG+f'ROW index={i} status={status}')
        rows.extend((subject.TAG+'DONE requested=4 ok=0 unavailable=1 no_sector=1 docked_or_stored=1 local_invalid=1 sectors=0 game=5',
                     subject.base.load.TAG.decode()+'pause_observed|'+fields))
        result=subject.validate(('\n'.join(rows)+'\n').encode(),ticket,1,limit=4)
        self.assertEqual([result[k] for k in ('position_reads','unavailable','no_sector','docked_or_stored','local_invalid')],
                         [0,1,1,1,1])
        self.assertFalse(result['position_observation_conclusive'])


if __name__=='__main__': unittest.main()
