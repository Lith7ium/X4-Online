"""Offline evidence and isolation checks for the single-process seat harness."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('player_seat_live', ROOT / 'tools/dev/authority_player_seat_live.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class PlayerSeatLiveTests(unittest.TestCase):
    def setUp(self):
        self.ticket = dict(world_epoch='a'*32, connection_handle=1, baseline_id=1,
                           load_generation=1, checkpoint_id=live.base.archive.CHECKPOINT_ID,
                           sha256=live.base.archive.SHA256, attempt_id='b'*32, slot='save_009')
        fields = '|'.join(str(self.ticket[k]) for k in live.base.load.FIELDS)
        tag = live.base.load.TAG.decode()
        self.baseline = [tag+'load_requested|'+fields,
                         '[X4LAN] AUTH_MARKER load INSPECTED '+live.base.archive.MARKER,
                         '[X4LAN] AUTH_SECTOR_READ DONE slot=2 pilot=present order=Patrol state=started game=3 x=1 y=2 z=3',
                         tag+'pause_observed|'+fields]
        self.steps = [live.TAG+x for x in live.STEPS]

    @staticmethod
    def raw(lines):
        return ('\n'.join(lines)+'\n').encode()

    def test_complete_and_every_partial_prefix(self):
        for end in range(len(self.steps)):
            self.assertIsNone(live.validate(self.raw(self.baseline+self.steps[:end]), self.ticket, 2, partial=True))
        result = live.validate(self.raw(self.baseline+self.steps), self.ticket, 2)
        self.assertTrue(result['diagnostic_completed'])
        self.assertTrue(result['positive_control_observed'])
        self.assertTrue(result['two_negative_observations'])
        self.assertFalse(result['seat_free_proven'])
        self.assertFalse(result['player_control_proven'])
        self.assertFalse(result['save_authorized'])
        self.assertFalse(result['multiplayer_proven'])

    def test_missing_duplicate_reordered_early_and_late_fault_fail(self):
        cases = [self.baseline+self.steps[:-1], self.baseline+self.steps+[self.steps[-1]],
                 self.baseline+[self.steps[1],self.steps[0]]+self.steps[2:],
                 self.baseline[:3]+self.steps+self.baseline[3:],
                 self.baseline+self.steps+[live.TAG+'ERROR late'],
                 self.baseline+self.steps+[self.steps[0]+' unexpected'],
                 self.baseline[:2]+[self.baseline[2].replace('pilot=present','pilot=absent')]+self.baseline[3:]+self.steps]
        for rows in cases:
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    live.validate(self.raw(rows), self.ticket, 2)
        with self.assertRaises(ValueError):
            live.validate(self.raw(self.baseline[:3]+[self.steps[0]]), self.ticket, 2, partial=True)
        self.assertIsNone(live.validate(b'incomplete', self.ticket, 2, partial=True))

    def test_install_hooks_single_owner_and_protects_every_new_file(self):
        with tempfile.TemporaryDirectory() as temp:
            case=Path(temp)/'case'; profile=case/'profile'; lab=case/'extensions/x4_lan_lab'
            ui=lab/'ui'; md=lab/'md'; ui.mkdir(parents=True); md.mkdir(); (profile/'save').mkdir(parents=True)
            for path in (ui/'native_gate_snapshot.lua', md/'native_gate_battle.xml', ui/'config.lua', ui/'sha256.lua',
                         lab/'content.xml', profile/'content.xml', profile/'config.xml'):
                path.write_text('test')
            protected=live.install(case, profile, self.ticket, 2, 90)
            self.assertTrue(set(md/name for name in live.MD).issubset(protected))
            self.assertTrue(set(ui/name for name in live.UI).issubset(protected))
            owner=(ui/'authority_download_load_probe.lua').read_text()
            self.assertEqual(owner.count("SetScript('onUpdate'"), 1)
            self.assertIn('X4LAN_PLAYER_SEAT_EXPERIMENT_TICK()',owner)
            manifest=(lab/'ui.xml').read_text()
            self.assertLess(manifest.index(live.UI[0]), manifest.index(live.UI[1]))
            self.assertLess(manifest.index(live.UI[1]), manifest.index('authority_download_load_probe.lua'))
            self.assertIn('X4LAN_SECTOR_READ_EXPORT()', (ui/'authority_sector_read_probe.lua').read_text())
            with self.assertRaises(ValueError): live.install(case, profile, self.ticket, 1, 90)
            with self.assertRaises(ValueError): live.install(case, profile, self.ticket, 2, 121)

    def test_supervisor_hooks_are_restored_and_final_source_change_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); store=root/'source'/'checkpoints'; store.mkdir(parents=True); out=root/'output'
            args=SimpleNamespace(slot=2, timeout=120, out=out, store=store)
            originals=(live.base.install,live.base.check_log_bytes,live.base.fault_log,
                       live.base.base.readonly_save_command,live.base.result_finalizer)
            def fake_run(_):
                self.assertIs(live.base.check_log_bytes,live.validate)
                self.assertIs(live.base.fault_log,live.fault)
                self.assertIs(live.base.base.readonly_save_command,live.readonly.readonly_save_command)
                result={'success':True}
                live.base.result_finalizer(result)
                return result
            with patch.object(live.base.snapshot,'output_path',return_value=out), \
                 patch.object(live.base.base,'local_directory',return_value=store), \
                 patch.object(live.base.archive,'_path_fingerprints',side_effect=[{'a':1},{'a':1}]), \
                 patch.object(live.base,'run',side_effect=fake_run):
                result=live.run(args)
            self.assertTrue(result['success'])
            self.assertFalse(result['seat_free_proven'])
            self.assertEqual(originals,(live.base.install,live.base.check_log_bytes,live.base.fault_log,
                                        live.base.base.readonly_save_command,live.base.result_finalizer))
            with patch.object(live.base.snapshot,'output_path',return_value=out), \
                 patch.object(live.base.base,'local_directory',return_value=store), \
                 patch.object(live.base.archive,'_path_fingerprints',side_effect=[{'a':1},{'a':2}]), \
                 patch.object(live.base,'run',side_effect=fake_run):
                with self.assertRaises(ValueError): live.run(args)
            self.assertEqual(originals,(live.base.install,live.base.check_log_bytes,live.base.fault_log,
                                        live.base.base.readonly_save_command,live.base.result_finalizer))


if __name__ == '__main__':
    unittest.main()
