"""Offline wrapper cleanup tests; no X4 processes are started."""
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_recovery_tcp_join_live as recovery
import authority_trusted_marked_live as marked
import authority_two_x4_resume_live as resume


class Participant:
    def __init__(self, config, *, close_fails=False):
        self.config = config
        self.close_fails = close_fails
        self.events = []

    def close(self):
        self.events.append('close')
        if self.close_fails:
            raise OSError('close failure')

    def redact(self):
        self.events.append('redact')
        self.config.write_text('redacted')

    def cleanup_before_owned_processes(self):
        self.events.append('cleanup')
        return True


class WrapperRedactionTests(unittest.TestCase):
    def test_wrappers_require_stop_evidence_and_preserve_cleanup_errors(self):
        for kind in ('marked', 'recovery', 'resume'):
            for state in ('confirmed', 'unconfirmed', 'missing', 'raises'):
                with self.subTest(kind=kind, state=state), tempfile.TemporaryDirectory() as directory:
                    out = Path(directory)
                    config = out / 'config.lua'; config.write_text('secret')
                    participant = Participant(config, close_fails=True)
                    result = {'success': False, 'cleanup_error': 'earlier cleanup error'}
                    if state != 'missing':
                        result['owned_cleanup_confirmed'] = state == 'confirmed'
                    outcome = ValueError('original failure') if state == 'raises' else result
                    with ExitStack() as stack:
                        def mock_outcome(*_args, **_kwargs):
                            if isinstance(outcome, BaseException):
                                raise outcome
                            return outcome
                        if kind == 'marked':
                            stack.enter_context(patch.object(marked, 'MarkedParticipant', return_value=participant))
                            stack.enter_context(patch.object(marked.base.snapshot, 'output_path', return_value=out))
                            stack.enter_context(patch.object(marked.base, 'run', side_effect=mock_outcome))
                            invoke = lambda: marked.run(SimpleNamespace(out=out))
                        elif kind == 'recovery':
                            stack.enter_context(patch.object(recovery, 'check_separate', return_value=(out, out/'store')))
                            stack.enter_context(patch.object(recovery, 'RecoveredParticipant', return_value=participant))
                            stack.enter_context(patch.object(recovery.base, 'run', side_effect=mock_outcome))
                            invoke = lambda: recovery.run(SimpleNamespace(out=out,timeout=10))
                        else:
                            stack.enter_context(patch.object(resume, 'Participant', return_value=participant))
                            stack.enter_context(patch.object(resume.base.snapshot, 'output_path', return_value=out))
                            stack.enter_context(patch.object(resume.identity, 'run', side_effect=mock_outcome))
                            invoke = lambda: resume.run(SimpleNamespace(out=out))
                        if state == 'raises':
                            with self.assertRaisesRegex(ValueError, 'original failure') as caught:
                                invoke()
                            self.assertTrue(any('close failure' in note for note in caught.exception.__notes__))
                            self.assertTrue(any('client config retained' in note for note in caught.exception.__notes__))
                        else:
                            returned = invoke()
                            self.assertFalse(returned['success'])
                            self.assertIn('earlier cleanup error', returned['cleanup_error'])
                            self.assertIn('close failure', returned['cleanup_error'])
                            if state != 'confirmed':
                                self.assertIn('client config retained', returned['cleanup_error'])
                    self.assertIn('close', participant.events)
                    self.assertEqual(config.read_text(), 'redacted' if state == 'confirmed' else 'secret')
                    self.assertEqual('redact' in participant.events, state == 'confirmed')


if __name__ == '__main__':
    unittest.main()
