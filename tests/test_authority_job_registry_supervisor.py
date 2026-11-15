"""The supervisor contract is exercised with doubles, without X4."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('job_supervisor', ROOT/'tools/dev/authority_job_registry_supervisor.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
EPOCH = 'a' * 32


def summary(count):
    return {'observed': count, 'acknowledged': count, 'baseline_count': 1,
            'classification': 'inconclusive_no_events' if not count else 'local_activations_observed',
            'birth_confirmed': False, 'delivery_confirmed': False, 'coverage': 'unknown'}


class SupervisorTest(unittest.TestCase):
    def run_case(self, responses, *, resume_fails=False, clean=True, owner=True):
        calls = []
        class Bridge:
            _timeout = 1
            def pause(self): calls.append('pause')
            def resume(self):
                calls.append('resume')
                if resume_fails: raise TimeoutError('uncertain resume')
        class Channel:
            def start(self): calls.append('start')
            def receive(self, timeout):
                calls.append('receive')
                if not responses: raise TimeoutError('missing receipt')
                return responses.pop(0)
        def cleanup(): calls.append('cleanup'); return clean
        def check(): calls.append('check'); return owner
        def run():
            return module.supervise(bridge=Bridge(), channel=Channel(), check_owner=check,
                                    cleanup=cleanup, epoch=EPOCH, timeout=30, bridge_timeout=1, clock=lambda: 1.)
        return run, calls

    def test_zero_events_is_inconclusive_and_final_pause_precedes_cleanup(self):
        run, calls = self.run_case([('done', summary(0))])
        result = run()
        self.assertEqual(result['classification'], 'inconclusive_no_events')
        self.assertTrue(result['native_pause_confirmed'] and result['owned_cleanup_confirmed'])
        self.assertLess(len(calls)-1-calls[::-1].index('pause'), calls.index('cleanup'))
        self.assertEqual(calls.count('pause'), 2)

    def test_event_is_only_local_observation(self):
        event = {'epoch': EPOCH, 'sequence': 1, 'index': 2, 'classification': 'new_registry_entry',
                 'birth_confirmed': False, 'delivery_confirmed': False}
        run, _ = self.run_case([('event', event), ('done', summary(1))])
        result = run()
        self.assertEqual(result['observed'], 1)
        self.assertEqual(result['events'], [{'sequence': 1, 'index': 2, 'classification': 'new_registry_entry'}])

    def test_uncertain_resume_or_missing_receipt_always_fences(self):
        for kwargs in ({'resume_fails': True}, {}):
            run, calls = self.run_case([], **kwargs)
            with self.assertRaises(RuntimeError): run()
            self.assertEqual(calls[-1], 'cleanup')
            self.assertEqual(calls.count('pause'), 1)

    def test_unconfirmed_cleanup_or_inconsistent_evidence_cannot_pass(self):
        run, calls = self.run_case([('done', summary(0))], clean=False)
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'): run()
        self.assertEqual(calls[-1], 'cleanup')
        run, calls = self.run_case([('done', summary(1))])
        with self.assertRaises(RuntimeError): run()
        self.assertEqual(calls[-1], 'cleanup')

    def test_insufficient_or_mismatched_bridge_timeout_never_dispatches(self):
        calls = []
        class Bridge:
            _timeout = 5
            def pause(self): calls.append('pause')
            def resume(self): calls.append('resume')
        for configured, overall in ((5, 6), (4, 30)):
            calls.clear()
            with self.subTest(configured=configured), self.assertRaises((ValueError, RuntimeError)):
                module.supervise(bridge=Bridge(), channel=object(), check_owner=lambda: True,
                    cleanup=lambda: calls.append('cleanup') or True, epoch=EPOCH, timeout=overall,
                    bridge_timeout=configured, clock=lambda: 1.)
            self.assertEqual(calls, ['cleanup'])

    def test_system_exit_still_cleans_up_and_preserves_original(self):
        calls = []
        class Bridge:
            _timeout = 1
            def pause(self): raise SystemExit('injected exit')
        with self.assertRaisesRegex(SystemExit, 'injected exit'):
            module.supervise(bridge=Bridge(), channel=object(), check_owner=lambda: True,
                cleanup=lambda: calls.append('cleanup') or True, epoch=EPOCH,
                timeout=30, bridge_timeout=1, clock=lambda: 1.)
        self.assertEqual(calls, ['cleanup'])

    def test_duplicate_new_classification_is_refused(self):
        event = {'epoch': EPOCH, 'sequence': 1, 'index': 2, 'classification': 'new_registry_entry',
                 'birth_confirmed': False, 'delivery_confirmed': False}
        duplicate = dict(event, sequence=2)
        run, calls = self.run_case([('event', event), ('event', duplicate), ('done', summary(2))])
        with self.assertRaises(RuntimeError): run()
        self.assertEqual(calls[-1], 'cleanup')

    def test_cleanup_failure_retains_prior_failure(self):
        run, _ = self.run_case([], resume_fails=True, clean=False)
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed') as caught: run()
        self.assertIsInstance(caught.exception.original_error, TimeoutError)
        self.assertIsNotNone(caught.exception.__cause__)

    def test_event_evidence_is_bounded(self):
        event = {'epoch': EPOCH, 'sequence': 1, 'index': 1, 'classification': 'new_registry_entry',
                 'birth_confirmed': False, 'delivery_confirmed': False}
        run, calls = self.run_case([('event', event)])
        old = module.MAX_EVENTS
        try:
            module.MAX_EVENTS = 0
            with self.assertRaises(RuntimeError): run()
        finally:
            module.MAX_EVENTS = old
        self.assertEqual(calls[-1], 'cleanup')
