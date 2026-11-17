"""Client registry correlation tests; no native process is started."""
from pathlib import Path
import gzip
import hashlib
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_recovered_client_registry as subject
import authority_recovered_server_client as owner
import authority_download_load_live as load
from unittest.mock import Mock, patch


class RecoveredClientRegistryTests(unittest.TestCase):
    nonce = 'a'*32
    marker = 'b'*32
    ticket = dict(world_epoch='c'*32, connection_handle=1, baseline_id=2,
                  load_generation=3, checkpoint_id='checkpoint-'+'d'*32,
                  sha256='e'*64, attempt_id='f'*32, slot='save_009')

    def test_status_gate_is_enabled_for_enrollment_as_well_as_status(self):
        self.assertFalse(owner.client_registry_enabled(SimpleNamespace()))
        self.assertTrue(owner.client_registry_enabled(SimpleNamespace(registry_status=True)))
        self.assertTrue(owner.client_registry_enabled(SimpleNamespace(registry_enroll=True)))

    def setup_case(self, root):
        lab = Path(root)/'extensions/x4_lan_lab'
        (lab/'ui').mkdir(parents=True); (lab/'md').mkdir()
        (lab/'ui.xml').write_text('<ui>\n    <file name="ui/authority_download_load_probe.lua" />\n</ui>\n')
        probe = (ROOT/'tools/dev/authority_download_load_probe.lua').read_text()
        hook = " elseif state=='observing' then\n"
        probe = probe.replace(hook, hook+'  if not X4LAN_AUTHORITY_MARKER_READY() then return end\n'
                              +'  if not X4LAN_IDENTITY_READY() then return end\n')
        (lab/'ui/authority_download_load_probe.lua').write_text(probe)
        return lab

    def test_installs_paused_status_gate_after_marker_and_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = self.setup_case(tmp)
            protected = subject.install(tmp, self.nonce, ('ready', '1'*32, 3, '2'*64))
            self.assertEqual({p.name for p in protected}, {'recovery_registry_status.lua', 'authority_ship_registry.xml'})
            probe = (lab/'ui/authority_download_load_probe.lua').read_text()
            for a, b in zip(('X4LAN_AUTHORITY_MARKER_READY()', 'X4LAN_IDENTITY_READY()',
                             'registry_pause_confirmed=true', 'registry_status:begin()', 'barrier.update()'),
                            ('X4LAN_IDENTITY_READY()', 'registry_pause_confirmed=true',
                             'registry_status:begin()', 'barrier.update()', "state='done'")):
                self.assertLess(probe.index(a), probe.index(b))
            self.assertIn("expected='"+'1'*32+"|3'", probe)
            self.assertIn('engine.pause()', probe)
            self.assertIn('AUTH_RECOVERY_REGISTRY_ERROR', probe)
            self.assertIn('if registry_pause_confirmed then error', probe)
            self.assertLess((lab/'ui.xml').read_text().index('recovery_registry_status.lua'),
                            (lab/'ui.xml').read_text().index('authority_download_load_probe.lua'))

    def test_invalid_hooks_leave_overlay_unchanged_and_retryable(self):
        hooks = (
            ('ui.xml', '    <file name="ui/authority_download_load_probe.lua" />\n'),
            ('ui/authority_download_load_probe.lua', "local state='initial';local failed=false\n"),
            ('ui/authority_download_load_probe.lua', '  if not X4LAN_IDENTITY_READY() then return end\n'),
        )
        for relative, hook in hooks:
            for replacement in ('', hook + hook):
                with self.subTest(path=relative, duplicate=bool(replacement)), tempfile.TemporaryDirectory() as tmp:
                    lab = self.setup_case(tmp)
                    target = lab / relative
                    original = target.read_text()
                    self.assertEqual(original.count(hook), 1)
                    target.write_text(original.replace(hook, replacement))
                    before = {path.relative_to(lab): path.read_bytes()
                              for path in lab.rglob('*') if path.is_file()}
                    with self.assertRaises(ValueError):
                        subject.install(tmp, self.nonce, ('ready', '1'*32, 3, '2'*64))
                    after = {path.relative_to(lab): path.read_bytes()
                             for path in lab.rglob('*') if path.is_file()}
                    self.assertEqual(after, before)
                    target.write_text(original)
                    self.assertEqual(len(subject.install(tmp, self.nonce, ('ready', '1'*32, 3, '2'*64))), 2)

    def test_rejects_invalid_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.setup_case(tmp)
            for nonce, status in [('bad', ('uninitialized',)), (self.nonce, ('ready', '1'*32, 0, '2'*64)),
                                  (self.nonce, ('ready', '1'*32, 1, 'bad'))]:
                with self.assertRaises(ValueError): subject.install(tmp, nonce, status)

    def rows(self, status):
        watch = load.ReceiptWatch('/unused', self.ticket)
        status_text = 'uninitialized' if status == ('uninitialized',) else status[1]+'|'+str(status[2])
        return [load.TAG+watch.expected[0], b'[X4LAN] AUTH_MARKER load INSPECTED '+self.marker.encode(),
                b'[X4LAN] AUTH_IDENTITY load READY',
                ('[X4LAN] AUTH_RECOVERY_REGISTRY '+self.nonce+'|startup|'+status_text).encode(),
                load.TAG+watch.expected[1]]

    def test_correlates_status_with_ordered_ticket_and_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log'
            for status in [('uninitialized',), ('ready', '1'*32, 3, '2'*64)]:
                rows = self.rows(status)
                path.write_bytes(b'\n'.join(rows)+b'\n')
                self.assertTrue(subject.verify_log(path, self.nonce, status, self.ticket, self.marker))
                for invalid in (rows[:-1], rows+[rows[3]], rows+[b'[X4LAN] AUTH_RECOVERY_REGISTRY '+self.nonce.encode()+b'|startup|wrong'],
                                rows[:2]+[rows[3],rows[2],rows[4]],
                                rows[:3]+[rows[3].replace(b'startup', b'other')]+rows[4:]):
                    path.write_bytes(b'\n'.join(invalid)+b'\n')
                    with self.assertRaises(ValueError):
                        subject.verify_log(path, self.nonce, status, self.ticket, self.marker)
                path.write_bytes(b'\n'.join(rows)+b'\n')
                with self.assertRaises(ValueError):
                    subject.verify_log(path, self.nonce, status, self.ticket, '9'*32)
                path.write_bytes(b'\n'.join(rows+[b'[X4LAN] AUTH_RECOVERY_REGISTRY_ERROR '+self.nonce.encode()])+b'\n')
                with self.assertRaisesRegex(ValueError, 'faulted'):
                    subject.verify_log(path, self.nonce, status, self.ticket, self.marker)

    def test_guard_rechecks_for_late_status_fault_before_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log'; status = ('uninitialized',)
            rows = self.rows(status);path.write_bytes(b'\n'.join(rows)+b'\n')
            check = Mock(return_value=True)
            verify = lambda: subject.verify_log(path, self.nonce, status, self.ticket, self.marker)
            self.assertTrue(owner.guarded_registry_observation(check, verify))
            self.assertEqual(check.call_count, 2)
            path.write_bytes(b'\n'.join(rows+[b'[X4LAN] AUTH_RECOVERY_REGISTRY_ERROR '+self.nonce.encode()])+b'\n')
            with self.assertRaisesRegex(ValueError, 'faulted'):
                owner.guarded_registry_observation(check, verify)

    def setup_marker_case(self, root):
        # Exercise the actual production marked-load installer, rather than
        # synthesizing its hook or passing the expected marker into Lua.
        lab = self.setup_case(root)
        probe = lab/'ui/authority_download_load_probe.lua'
        text = probe.read_text()
        text = text.replace('  if not X4LAN_AUTHORITY_MARKER_READY() then return end\n', '')
        text = text.replace('  if not X4LAN_IDENTITY_READY() then return end\n', '')
        probe.write_text(text)
        (lab/'ui/config.lua').write_text('X4LAN_CONFIG = {enabled=false}\n')
        subject.recovery.marked.install_marked_load_probe(Path(root))
        return lab

    def snapshot_overlay(self, lab):
        return {path.relative_to(lab): path.read_bytes()
                for path in lab.rglob('*') if path.is_file()}

    def marker_rows(self, status):
        return [row for row in self.rows(status) if b'AUTH_IDENTITY' not in row]

    def test_installs_optional_registry_after_real_marked_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = self.setup_marker_case(tmp)
            status = ('ready', '1'*32, 3, '2'*64)
            protected = subject.install(tmp, self.nonce, status, load_gate='marker')
            self.assertEqual(len(protected), 2)
            probe = (lab/'ui/authority_download_load_probe.lua').read_text()
            self.assertNotIn('X4LAN_IDENTITY_READY', probe)
            self.assertLess(probe.index('X4LAN_AUTHORITY_MARKER_READY()'),
                            probe.index('registry_pause_confirmed=true'))
            self.assertLess(probe.index('registry_status:ready()'), probe.index('barrier.update()'))
            self.assertIn("expected='"+'1'*32+"|3'", probe)
            self.assertIn('if registry_pause_confirmed then error', probe)
            self.assertIn("RegisterEvent('X4AuthorityShipRegistry.Correlated'", probe)
            self.assertNotIn(self.marker, probe)
            self.assertNotIn(self.marker, (lab/'ui/config.lua').read_text())

    def test_marker_gate_missing_duplicate_or_mixed_leaves_overlay_unchanged(self):
        hook = '  if not X4LAN_AUTHORITY_MARKER_READY() then return end\n'
        for replacement in ('', hook+hook, hook+'  if not X4LAN_IDENTITY_READY() then return end\n'):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as tmp:
                lab = self.setup_marker_case(tmp)
                probe = lab/'ui/authority_download_load_probe.lua'
                probe.write_text(probe.read_text().replace(hook, replacement))
                before = self.snapshot_overlay(lab)
                with self.assertRaises(ValueError):
                    subject.install(tmp, self.nonce, ('uninitialized',), load_gate='marker')
                self.assertEqual(self.snapshot_overlay(lab), before)

    def test_invalid_gate_rejected_before_install_or_log_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = self.setup_marker_case(tmp)
            before = self.snapshot_overlay(lab)
            for mode in ('', 'marked', None, True, []):
                with self.subTest(mode=mode):
                    with self.assertRaisesRegex(ValueError, 'load gate'):
                        subject.install(tmp, self.nonce, ('uninitialized',), load_gate=mode)
                    self.assertEqual(self.snapshot_overlay(lab), before)
                    with self.assertRaisesRegex(ValueError, 'load gate'):
                        subject.verify_log(Path(tmp)/'absent', self.nonce, ('uninitialized',),
                                           self.ticket, self.marker, load_gate=mode)

    def test_marker_log_requires_exact_unique_ordered_receipts_without_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log'
            for status in (('uninitialized',), ('ready', '1'*32, 3, '2'*64)):
                rows = self.marker_rows(status)
                path.write_bytes(b'\n'.join(rows)+b'\n')
                self.assertTrue(subject.verify_log(path, self.nonce, status, self.ticket,
                                                   self.marker, load_gate='marker'))
                cases = []
                for index in range(len(rows)):
                    cases.append(rows[:index]+rows[index+1:])
                    cases.append(rows[:index]+[rows[index]]+rows[index:])
                    cases.append(rows[:index]+[rows[index]+b'extra']+rows[index+1:])
                for index in range(len(rows)-1):
                    swapped = list(rows)
                    swapped[index], swapped[index+1] = swapped[index+1], swapped[index]
                    cases.append(swapped)
                cases.extend([
                    self.rows(status),
                    rows+[b'[X4LAN] AUTH_MARKER load ERROR'],
                    rows+[b'[X4LAN] AUTH_RECOVERY_REGISTRY '+self.nonce.encode()+b'|startup|wrong'],
                    rows+[b'[X4LAN] AUTH_RECOVERY_REGISTRY_ERROR '+self.nonce.encode()],
                    rows+[b'X'*(load.ReceiptWatch.MAX_LINE+1)],
                ])
                for index, invalid in enumerate(cases):
                    with self.subTest(status=status, case=index):
                        path.write_bytes(b'\n'.join(invalid)+b'\n')
                        with self.assertRaises(ValueError):
                            subject.verify_log(path, self.nonce, status, self.ticket,
                                               self.marker, load_gate='marker')
                path.write_bytes(b'\n'.join(rows))
                with self.assertRaisesRegex(ValueError, 'incomplete'):
                    subject.verify_log(path, self.nonce, status, self.ticket,
                                       self.marker, load_gate='marker')

    def test_marker_log_rechecks_stability_and_late_fault(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log'
            status = ('uninitialized',)
            rows = self.marker_rows(status)
            path.write_bytes(b'\n'.join(rows)+b'\n')
            verify = lambda: subject.verify_log(path, self.nonce, status, self.ticket,
                                               self.marker, load_gate='marker')
            self.assertTrue(owner.guarded_registry_observation(Mock(return_value=True), verify))
            evidence = subject.recovery.marked.file_evidence
            original = evidence._read_regular
            calls = []
            def changing_read(*args, **kwargs):
                calls.append(True)
                if len(calls) == 2:
                    with path.open('ab') as stream:
                        stream.write(b'[X4LAN] AUTH_RECOVERY_REGISTRY_ERROR '+self.nonce.encode()+b'\n')
                return original(*args, **kwargs)
            with patch.object(evidence, '_read_regular', side_effect=changing_read):
                with self.assertRaisesRegex(ValueError, 'changed'):
                    verify()
            with self.assertRaisesRegex(ValueError, 'faulted'):
                owner.guarded_registry_observation(Mock(return_value=True), verify)

    def test_checkpoint_parse_pumps_tcp_owner_and_propagates_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'save.xml.gz';path.write_bytes(gzip.compress(b'<savegame/>'))
            checkpoint=SimpleNamespace(checkpoint_id='checkpoint-'+'1'*32, path=path,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size=path.stat().st_size, marker='2'*32)
            participant=SimpleNamespace(pump_loading=Mock(), helpers=[]);check=Mock(return_value=True)
            self.assertEqual(owner.read_registry_while_pumping(participant, checkpoint, time.monotonic()+5, check),
                             ('uninitialized',))
            self.assertGreater(participant.pump_loading.call_count, 0)
            self.assertEqual(check.call_count, 2)
            self.assertEqual(participant.helpers[-1].proc.returncode, 0)
            self.assertIsNone(participant.helpers[-1].pidfd)
            checkpoint.sha256='0'*64
            with self.assertRaises(RuntimeError):
                owner.read_registry_while_pumping(participant, checkpoint, time.monotonic()+5, check)
            self.assertIsNotNone(participant.helpers[-1].proc.returncode)
            self.assertIsNone(participant.helpers[-1].pidfd)

    def test_hung_parser_is_killed_and_reaped_on_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker=Path(tmp)/'hang.py'
            worker.write_text('import signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\ntime.sleep(30)\n')
            checkpoint=SimpleNamespace(checkpoint_id='checkpoint-'+'1'*32,path=Path(tmp)/'save.xml.gz',
                                       sha256='0'*64,size=1,marker='2'*32)
            participant=SimpleNamespace(pump_loading=Mock(),helpers=[])
            started=time.monotonic()
            with patch.object(owner, 'REGISTRY_READER', worker):
                with self.assertRaises(TimeoutError):
                    owner.read_registry_while_pumping(participant, checkpoint, started+1.4, Mock(return_value=True))
            self.assertLess(time.monotonic()-started, 5)
            self.assertIsNotNone(participant.helpers[-1].proc.returncode)
            self.assertIsNone(participant.helpers[-1].pidfd)


if __name__ == '__main__': unittest.main()
