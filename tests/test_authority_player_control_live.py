"""Offline supervisor contract checks. Importing these tests never starts X4."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('player_control_live', ROOT / 'tools/dev/authority_player_control_live.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class PlayerControlLiveTests(unittest.TestCase):
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
        self.controlled = ('START', 'CREATED', 'BEFORE', 'INTENT_TELEPORT',
                           'LOCAL_CALL_RETURNED', 'DISPATCH', 'FIRST', 'CONTROLLED', 'DONE')

    @staticmethod
    def raw(lines):
        return ('\n'.join(lines)+'\n').encode()

    def check(self, steps, *, partial=False):
        lines = []
        for step in steps:
            if step == 'DISPATCH':
                lines += [live.MD_TAG+'ACTION_BEGIN', live.MD_TAG+'ACTION_RETURNED']
            lines.append(live.TAG+step)
        return live.validate(self.raw(self.baseline+lines), self.ticket, 2, partial=partial)

    def test_controlled_and_all_inconclusive_prefixes(self):
        outcomes = [(self.controlled, 'controlled')]
        outcomes += [(self.controlled[:n]+('INCONCLUSIVE', 'DONE'), 'inconclusive') for n in range(1, 8)]
        for steps, expected in outcomes:
            with self.subTest(steps=steps):
                for end in range(len(steps)):
                    self.assertIsNone(self.check(steps[:end], partial=True))
                result = self.check(steps)
                self.assertEqual(result['outcome'], expected)
                self.assertIs(result['diagnostic_completed'], True)
                self.assertIs(result['local_control_proven'], expected == 'controlled')
                for key in ('flight_proven', 'seat_free_proven', 'save_authorized', 'multiplayer_proven'):
                    self.assertIs(result[key], False)

    def test_missing_reordered_duplicated_late_or_unknown_receipts_fail(self):
        cases = [('START',), ('CREATED',), ('START','BEFORE'), ('START','START'),
                 ('START','CREATED','INCONCLUSIVE','DONE','DONE'),
                 ('START','CREATED','INCONCLUSIVE','CONTROLLED','DONE'),
                 self.controlled[:-1]+('INCONCLUSIVE','DONE'),
                 self.controlled+('CREATED',), ('START extra',), ('START','ERROR FAULT')]
        for steps in cases:
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                self.check(steps)
        with self.assertRaises(ValueError):
            live.validate(self.raw(self.baseline[:3]+[live.TAG+'START']), self.ticket, 2, partial=True)
        with self.assertRaises(ValueError):
            live.validate(self.raw(self.baseline+[live.TAG+'START', '[X4LAN] AUTH_PLAYER_CONTROL_LIVE ERROR FAULT']), self.ticket, 2, partial=True)
        self.assertIsNone(live.validate(b'incomplete', self.ticket, 2, partial=True))

    def test_expression_parse_error_before_start_or_after_done_is_rejected(self):
        parse = (r'[=ERROR=] 3.01 extensions\x4_lan_lab\md\authority_player_control_once.xml(36): '
                 'Error while parsing expression: Maximum operator nesting level reached')
        valid = self.baseline + [live.TAG+s for s in self.controlled[:5]] + [
            live.MD_TAG+'ACTION_BEGIN', live.MD_TAG+'ACTION_RETURNED'] + [live.TAG+s for s in self.controlled[5:]]
        for lines in ([parse] + self.baseline, valid + [parse],
                      self.baseline + ['[=ERROR=] Maximum operator nesting level reached']):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                live.validate(self.raw(lines), self.ticket, 2, partial=True)
        # Normal mention of expression parsing is not an engine parse error.
        benign = valid + ['[General] Expression parser available for player control']
        self.assertEqual(live.validate(self.raw(benign), self.ticket, 2)['outcome'], 'controlled')

    def test_md_markers_must_follow_intent_and_precede_dispatch(self):
        owner = lambda s: live.TAG+s
        begin, returned = live.MD_TAG+'ACTION_BEGIN', live.MD_TAG+'ACTION_RETURNED'
        prefix = [owner(s) for s in self.controlled[:5]]
        suffix = [owner(s) for s in self.controlled[5:]]
        # MD execution can finish while the Lua call is still returning.
        interleaved = prefix[:4] + [begin, returned] + prefix[4:] + suffix
        self.assertEqual(live.validate(self.raw(self.baseline+interleaved), self.ticket, 2)['outcome'], 'controlled')
        bad = [prefix+suffix, [begin]+prefix+[returned]+suffix,
               prefix+[returned,begin]+suffix, prefix+[begin,begin,returned]+suffix,
               prefix+[begin]+suffix+[returned],
               prefix+[owner('INCONCLUSIVE'),begin,owner('DONE')]]
        for lines in bad:
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                live.validate(self.raw(self.baseline+lines), self.ticket, 2)

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
            self.assertIn('X4LAN_PLAYER_CONTROL_LIVE_TICK()', owner)
            manifest = (lab/'ui.xml').read_text()
            self.assertLess(manifest.index(live.UI[0]), manifest.index(live.UI[1]))
            self.assertLess(manifest.index(live.UI[1]), manifest.index('authority_download_load_probe.lua'))
            self.assertIn('X4LAN_SECTOR_READ_EXPORT()', (ui/'authority_sector_read_probe.lua').read_text())
            config = (ui/'config.lua').read_text()
            self.assertIn('authority_player_control_live=true', config)
            self.assertRegex(config, r'authority_player_control_nonce="[a-f0-9]{32}"')
            with self.assertRaises(ValueError): live.install(case, profile, self.ticket, 1, 90)
            with self.assertRaises(ValueError): live.install(case, profile, self.ticket, 2, 121)

    def test_supervisor_final_archive_fence_restores_hooks(self):
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
                result = holder['result'] = {'success': True, 'outcome': 'controlled',
                                             'diagnostic_completed': True, 'local_control_proven': True}
                live.base.result_finalizer(result)
                return result
            common = (patch.object(live.base.snapshot,'output_path',return_value=out),
                      patch.object(live.base.base,'local_directory',return_value=store),
                      patch.object(live.base,'run',side_effect=fake_run))
            with common[0], common[1], common[2], patch.object(live.base.archive,'_path_fingerprints',side_effect=[{'a':1},{'a':1}]):
                result=live.run(args)
            self.assertEqual(result['outcome'], 'controlled')
            self.assertIs(result['local_control_proven'], True)
            self.assertIs(result['save_authorized'], False)
            self.assertEqual(originals,(live.base.install,live.base.check_log_bytes,live.base.fault_log,
                                        live.base.base.readonly_save_command,live.base.result_finalizer))
            with common[0], common[1], common[2], patch.object(live.base.archive,'_path_fingerprints',side_effect=[{'a':1},{'a':2}]):
                with self.assertRaises(ValueError): live.run(args)
            self.assertNotIn('outcome', holder['result'])
            self.assertNotIn('diagnostic_completed', holder['result'])
            self.assertIs(holder['result']['local_control_proven'], False)
            self.assertEqual(originals,(live.base.install,live.base.check_log_bytes,live.base.fault_log,
                                        live.base.base.readonly_save_command,live.base.result_finalizer))

    def test_failed_supervision_cannot_report_control(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); store=root/'source'/'checkpoints'; store.mkdir(parents=True); out=root/'output'
            args=SimpleNamespace(slot=2, timeout=120, out=out, store=store)
            def fake_run(_):
                result={'success':False,'outcome':'controlled','diagnostic_completed':True,'local_control_proven':True}
                live.base.result_finalizer(result)
                return result
            with patch.object(live.base.snapshot,'output_path',return_value=out), \
                 patch.object(live.base.base,'local_directory',return_value=store), \
                 patch.object(live.base.archive,'_path_fingerprints',side_effect=[{'a':1},{'a':1}]), \
                 patch.object(live.base,'run',side_effect=fake_run):
                result=live.run(args)
            self.assertNotIn('outcome',result)
            self.assertNotIn('diagnostic_completed',result)
            self.assertIs(result['local_control_proven'], False)


if __name__ == '__main__':
    unittest.main()
