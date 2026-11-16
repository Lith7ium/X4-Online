"""Offline contract checks; importing these tests never starts X4."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('positive_seat_live', ROOT / 'tools/dev/authority_positive_seat_live.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class PositiveSeatLiveTests(unittest.TestCase):
    def setUp(self):
        self.ticket = dict(world_epoch='a'*32, connection_handle=1, baseline_id=1,
                           load_generation=1, checkpoint_id=live.base.archive.CHECKPOINT_ID,
                           sha256=live.base.archive.SHA256, attempt_id='b'*32, slot='save_009')
        fields = '|'.join(str(self.ticket[k]) for k in live.base.load.FIELDS)
        tag = live.base.load.TAG.decode()
        self.baseline = [tag+'load_requested|'+fields,
                         '[X4LAN] AUTH_MARKER load INSPECTED '+live.base.archive.MARKER,
                         '[X4LAN] AUTH_SECTOR_READ DONE slot=2 pilot=absent order=none state=none game=3 x=1 y=2 z=3',
                         tag+'pause_observed|'+fields]

    @staticmethod
    def raw(lines):
        return ('\n'.join(lines)+'\n').encode()

    def test_both_outcomes_and_partial_prefixes(self):
        for outcome in ('CANDIDATE', 'INCONCLUSIVE'):
            steps = [live.TAG+'START', live.TAG+outcome, live.TAG+'DONE']
            for end in range(len(steps)):
                self.assertIsNone(live.validate(self.raw(self.baseline+steps[:end]), self.ticket, 2, partial=True))
            result = live.validate(self.raw(self.baseline+steps), self.ticket, 2)
            self.assertEqual(result['outcome'], outcome.lower())
            self.assertTrue(result['diagnostic_completed'])
            for key in ('seat_free_proven', 'player_control_proven', 'same_actor_proven',
                        'coverage_proven', 'save_authorized', 'multiplayer_proven'):
                self.assertIs(result[key], False)

    def test_receipt_order_integrity_and_faults_fail_closed(self):
        start, candidate, inconclusive, done = [live.TAG+s for s in ('START', 'CANDIDATE', 'INCONCLUSIVE', 'DONE')]
        cases = [self.baseline+[start,candidate], self.baseline+[start,candidate,done,done],
                 self.baseline+[candidate,start,done], self.baseline+[start,candidate,inconclusive,done],
                 self.baseline[:3]+[start]+self.baseline[3:]+[candidate,done],
                 self.baseline+[start,candidate,done,live.TAG+'ERROR'],
                 self.baseline+[start,live.TAG+'CANDIDATE extra',done],
                 self.baseline[:1]+[self.baseline[2],self.baseline[1]]+self.baseline[3:]+[start,candidate,done]]
        for lines in cases:
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                live.validate(self.raw(lines), self.ticket, 2)
        with self.assertRaises(ValueError):
            live.validate(self.raw(self.baseline[:3]+[start]), self.ticket, 2, partial=True)
        self.assertIsNone(live.validate(b'incomplete', self.ticket, 2, partial=True))

    def test_install_private_hooks_and_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            case = Path(temp)/'case'; profile = case/'profile'; lab = case/'extensions/x4_lan_lab'
            ui = lab/'ui'; md = lab/'md'; ui.mkdir(parents=True); md.mkdir(); (profile/'save').mkdir(parents=True)
            for path in (ui/'native_gate_snapshot.lua', md/'native_gate_battle.xml', ui/'config.lua', ui/'sha256.lua',
                         lab/'content.xml', profile/'content.xml', profile/'config.xml'):
                path.write_text('test')
            protected = live.install(case, profile, self.ticket, 2, 90)
            self.assertTrue(set(md/name for name in live.MD).issubset(protected))
            self.assertTrue(set(ui/name for name in live.UI).issubset(protected))
            owner = (ui/'authority_download_load_probe.lua').read_text()
            self.assertEqual(owner.count("SetScript('onUpdate'"), 1)
            self.assertIn('X4LAN_POSITIVE_SEAT_LIVE_TICK()', owner)
            manifest = (lab/'ui.xml').read_text()
            self.assertLess(manifest.index(live.UI[0]), manifest.index(live.UI[1]))
            self.assertLess(manifest.index(live.UI[1]), manifest.index('authority_download_load_probe.lua'))
            self.assertIn('X4LAN_SECTOR_READ_EXPORT()', (ui/'authority_sector_read_probe.lua').read_text())
            self.assertIn('authority_positive_seat_live=true', (ui/'config.lua').read_text())
            with self.assertRaises(ValueError): live.install(case, profile, self.ticket, 1, 90)
            with self.assertRaises(ValueError): live.install(case, profile, self.ticket, 2, 121)

    def test_supervisor_hooks_final_source_fence_and_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); store=root/'source'/'checkpoints'; store.mkdir(parents=True); out=root/'output'
            args=SimpleNamespace(slot=2, timeout=120, out=out, store=store)
            originals=(live.base.install,live.base.check_log_bytes,live.base.fault_log,
                       live.base.base.readonly_save_command,live.base.result_finalizer)
            holder = {}
            def fake_run(_):
                self.assertIs(live.base.check_log_bytes,live.validate)
                self.assertIs(live.base.fault_log,live.fault)
                self.assertIs(live.base.base.readonly_save_command,live.readonly.readonly_save_command)
                result = holder['result'] = {'success': True, 'outcome': 'candidate', 'diagnostic_completed': True}
                live.base.result_finalizer(result)
                return result
            common = (patch.object(live.base.snapshot,'output_path',return_value=out),
                      patch.object(live.base.base,'local_directory',return_value=store),
                      patch.object(live.base,'run',side_effect=fake_run))
            with common[0], common[1], common[2], patch.object(live.base.archive,'_path_fingerprints',side_effect=[{'a':1},{'a':1}]):
                result=live.run(args)
            self.assertEqual(result['outcome'], 'candidate')
            self.assertIs(result['save_authorized'], False)
            self.assertEqual(originals,(live.base.install,live.base.check_log_bytes,live.base.fault_log,
                                        live.base.base.readonly_save_command,live.base.result_finalizer))
            with common[0], common[1], common[2], patch.object(live.base.archive,'_path_fingerprints',side_effect=[{'a':1},{'a':2}]):
                with self.assertRaises(ValueError): live.run(args)
            self.assertNotIn('outcome', holder['result'])
            self.assertNotIn('diagnostic_completed', holder['result'])
            self.assertEqual(originals,(live.base.install,live.base.check_log_bytes,live.base.fault_log,
                                        live.base.base.readonly_save_command,live.base.result_finalizer))

    def test_failed_supervision_discards_diagnostic_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); store=root/'source'/'checkpoints'; store.mkdir(parents=True); out=root/'output'
            args=SimpleNamespace(slot=2, timeout=120, out=out, store=store)
            def fake_run(_):
                result={'success':False,'outcome':'inconclusive','diagnostic_completed':True}
                live.base.result_finalizer(result)
                return result
            with patch.object(live.base.snapshot,'output_path',return_value=out), \
                 patch.object(live.base.base,'local_directory',return_value=store), \
                 patch.object(live.base.archive,'_path_fingerprints',side_effect=[{'a':1},{'a':1}]), \
                 patch.object(live.base,'run',side_effect=fake_run):
                result=live.run(args)
            self.assertNotIn('outcome',result)
            self.assertNotIn('diagnostic_completed',result)


if __name__ == '__main__':
    unittest.main()
