"""Offline checks for the isolated marked-load diagnostic; no X4 launched."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import authority_trusted_marked_live as live


class MarkedHarnessTest(unittest.TestCase):
    def test_client_probe_waits_for_marker_and_installs_current_cue(self):
        participant = live.MarkedParticipant()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); case = root / 'client/case'
                lab = case / 'extensions/x4_lan_lab'; ui = lab / 'ui'
                ui.mkdir(parents=True); (lab / 'md').mkdir(); (lab / 'native').mkdir()
                (ui / 'config.lua').write_text('X4LAN_CONFIG = {}\n')
                (ui / 'authority_download_load_probe.lua').write_text(" elseif state=='observing' then\n")
                native = root / 'server/case/extensions/x4_lan_lab/native/x4lan_net.so'
                native.parent.mkdir(parents=True); native.write_bytes(b'test library')
                participant.install(case)
                self.assertIn('X4LAN_AUTHORITY_MARKER_READY()',
                              (ui / 'authority_download_load_probe.lua').read_text())
                self.assertIn('name="MarkerState"', (lab / 'md/authority_checkpoint_marker.xml').read_text())
                manifest = (lab / 'ui.xml').read_text()
                self.assertLess(manifest.index('ui/authority_checkpoint_marker_probe.lua'),
                                manifest.index('ui/authority_download_load_probe.lua'))
                self.assertIn('authority_marker_phase="load"', (ui / 'config.lua').read_text())
                participant.redact()
        finally:
            participant.close()

    def test_guarded_engine_limits_each_call_and_restores_timeout(self):
        calls = []
        class Engine:
            _timeout = 130
            def pause(self): calls.append(self._timeout)
        engine = Engine()
        with patch.object(live.time, 'monotonic', return_value=10):
            guarded = live.GuardedEngine(engine, lambda: calls.append('guard'), 16)
            guarded.pause()
        self.assertEqual(calls, ['guard', 5, 'guard'])
        self.assertEqual(engine._timeout, 130)

    def test_log_snapshot_requires_exact_order_and_complete_marker(self):
        ticket = dict(world_epoch='epoch', connection_handle=1, baseline_id=1, load_generation=1,
                      checkpoint_id='checkpoint-'+'a'*32, sha256='b'*64, attempt_id='c'*32, slot='save_009')
        with tempfile.TemporaryDirectory() as tmp:
            server = Path(tmp) / 'server'; client = Path(tmp) / 'client'
            server.write_bytes(b'server\n')
            watch = live.base.client.ReceiptWatch(client, ticket)
            marker = 'd' * 32
            content = (live.base.client.TAG + watch.expected[0] + b'\nAUTH_MARKER load INSPECTED '
                       + marker.encode() + b'\n' + live.base.client.TAG + watch.expected[1] + b'\n')
            self.assertIsNone(live.validate_client_receipts(content, ticket, marker))
            with patch.object(live.identity_evidence, 'observations_bytes', return_value=[{'name': 'n', 'macro': 'm'}]):
                client.write_bytes(content)
                live.observe_logs(server, client, ticket, marker)
                for bad in (content.replace(marker.encode(), marker.encode() + b'0'),
                            content + b'AUTH_MARKER load ERROR\n', content[:-1]):
                    client.write_bytes(bad)
                    with self.assertRaises(ValueError): live.observe_logs(server, client, ticket, marker)

    def test_admission_record_survives_later_failure(self):
        result = {'client_admitted': False}
        session = SimpleNamespace(accept=lambda connection, claim: None)
        with self.assertRaises(RuntimeError):
            live.accept_claim(session, object(), object(), result)
            raise RuntimeError('later control failed')
        self.assertTrue(result['client_admitted'])

    def test_partially_failed_admission_is_reported_as_indeterminate(self):
        result = {'client_admitted': False}; states = []
        def partial(connection, claim):
            states.append('peer may already be ready')
            raise RuntimeError('after mutation')
        with self.assertRaisesRegex(RuntimeError, 'after mutation'):
            live.accept_claim(SimpleNamespace(accept=partial), object(), object(), result)
        self.assertEqual(states, ['peer may already be ready'])
        self.assertIsNone(result['client_admitted'])
        self.assertEqual(result['admission_state'], 'indeterminate')

    def test_close_failure_preserves_original_error_and_retains_unfenced_config(self):
        calls = []
        class Participant:
            config = Path('/private/config.lua')
            def close(self): calls.append('close'); raise OSError('close failed')
            def redact(self): calls.append('redact')
        with patch.object(live, 'MarkedParticipant', return_value=Participant()), \
             patch.object(live.base.snapshot, 'output_path', return_value=Path('/unused')), \
             patch.object(live.base, 'run', side_effect=ValueError('original')):
            with self.assertRaisesRegex(ValueError, 'original') as context:
                live.run(SimpleNamespace(out='/unused'))
        self.assertEqual(calls, ['close'])
        self.assertTrue(any('close failed' in note for note in context.exception.__notes__))
        self.assertTrue(any('client config retained' in note for note in context.exception.__notes__))

    def test_close_failure_does_not_skip_confirmed_safe_redaction(self):
        calls = []
        class Participant:
            config = Path('/private/config.lua')
            def close(self): calls.append('close'); raise OSError('close failed')
            def redact(self): calls.append('redact')
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(live, 'MarkedParticipant', return_value=Participant()), \
             patch.object(live.base.snapshot, 'output_path', return_value=Path(tmp)), \
             patch.object(live.base, 'run', return_value={'success':False,'owned_cleanup_confirmed':True}):
            result=live.run(SimpleNamespace(out=tmp))
        self.assertEqual(calls,['close','redact'])
        self.assertIn('close failed',result['cleanup_error'])


if __name__ == '__main__': unittest.main()
