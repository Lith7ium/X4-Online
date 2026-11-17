"""Synthetic integration of the opt-in retained-client measurement."""
from pathlib import Path
import sys
import hashlib
import json
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_overlap_process_measurement as measurement
import authority_recovered_loopback_server as supervisor
import authority_recovered_server_client as client


class OverlapProcessMeasurementTest(unittest.TestCase):
    def test_option_is_explicit_bounded_and_overlap_only(self):
        self.assertIsNone(supervisor.diagnostic_process_measure_seconds(SimpleNamespace()))
        self.assertEqual(supervisor.diagnostic_process_measure_seconds(SimpleNamespace(
            diagnostic_process_measure_seconds=5, diagnostic_overlap=True)), 5)
        for duration, overlap in [(4, True), (301, True), (float('nan'), True), (5, False), (True, True)]:
            with self.assertRaises(ValueError):
                supervisor.diagnostic_process_measure_seconds(SimpleNamespace(
                    diagnostic_process_measure_seconds=duration, diagnostic_overlap=overlap))

    def test_fresh_sampler_uses_owned_identities_and_clock(self):
        calls = []
        clock = SimpleNamespace(sample=lambda deadline, tick, check: (check(), calls.append('clock'), 1.0)[2])
        def measure(**kwargs):
            self.assertTrue(kwargs['enabled'])
            self.assertEqual(kwargs['read_running_game_time'](), 1.0)
            self.assertEqual(kwargs['duration_seconds'], 5)
            return {'game_time_before': 1.0, 'game_time_after': 2.0, 'elapsed_seconds': 5,
                    'samples': [{'interval_seconds':None}] + [{'interval_seconds':1}] * 5,
                    'frame_times_measured':False}
        with patch.object(measurement, 'LinuxProcSampler', return_value=object()) as sampler, \
             patch.object(measurement, 'measure_running_window', side_effect=measure):
            result = measurement.measure_single_client_phase(server_identity=(11, 1), client_identity=(22, 2),
                supervisor_identity=(33, 3), clock=clock, tick=lambda:None, check=lambda:None,
                duration=5, deadline=10)
        sampler.assert_called_once_with({'server_x4':(11, 1), 'client_x4':(22, 2), 'supervisor':(33, 3)})
        self.assertEqual(result['owner_context_checks'], 1)
        self.assertEqual(result['process_identities']['client_x4'], {'pid':22, 'start_ticks':2})
        self.assertTrue(result['diagnostic_cpu_and_io_included'])
        self.assertFalse(result['frame_times_measured'])

    def test_short_or_missing_sample_intervals_are_rejected(self):
        for elapsed, samples in [(4, [None, 1, 1, 1]), (5, [None, 1, 1]), (5, [None, 1, None, 1])]:
            output={'elapsed_seconds':elapsed, 'samples':[{'interval_seconds':value} for value in samples]}
            with patch.object(measurement, 'LinuxProcSampler'), \
                 patch.object(measurement, 'measure_running_window', return_value=output):
                with self.assertRaisesRegex(ValueError, 'too short'):
                    measurement.measure_single_client_phase(server_identity=(1, 1), client_identity=(2, 2),
                        supervisor_identity=(3, 3), clock=object(), tick=lambda:None, check=lambda:None,
                        duration=5, deadline=10)

    def test_report_is_separate_exact_and_cannot_overwrite(self):
        report = {'phase':'after_first_admission_before_second_join', 'game_time_before':1,
                  'game_time_after':2, 'elapsed_seconds':5, 'samples':[{'thread':1}],
                  'process_identities':{'server_x4':{'pid':11,'start_ticks':1}}}
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            summary = measurement.write_report(out, report)
            contents = (out / summary['report']).read_bytes()
            self.assertEqual(hashlib.sha256(contents).hexdigest(), summary['sha256'])
            self.assertEqual(json.loads(contents), report)
            self.assertNotIn('samples', summary)
            self.assertTrue(summary['enclosing_run_final_checks_required'])
            with self.assertRaises(FileExistsError):
                measurement.write_report(out, report)
            self.assertEqual((out / summary['report']).read_bytes(), contents)
            self.assertFalse((out / 'process-measurement.json.tmp').exists())

    def test_first_fixture_pin_binds_exact_two_owned_paths(self):
        from authority_fixture_save_guards import FixtureSaveGuards, FixtureSamplingWindow
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            server = out / 'server-save'
            client_save = out / 'overlap-01/client/case/home/.config/EgoSoft/X4/45841/save/save_009.xml.gz'
            client_save.parent.mkdir(parents=True)
            entries = []
            for path, data in ((server,b'server'), (client_save,b'client')):
                path.write_bytes(data); path.chmod(0o400)
                entries.append((path, hashlib.sha256(data).hexdigest()))
            active = SimpleNamespace(save_target=client_save, save_digest=entries[1][1])
            guards = FixtureSaveGuards(lambda path: hashlib.sha256(path.read_bytes()).hexdigest())
            def verify():
                for entry in entries:
                    self.assertTrue(guards.check(*entry))
            window = FixtureSamplingWindow(guards, verify, lambda:True)
            supervisor.open_first_fixture_sampling_window(window, active_clients=[active], active=active,
                out=out, server_save=server, server_digest=entries[0][1])
            with self.assertRaisesRegex(ValueError, 'outside'):
                guards.check(out / 'foreign', entries[1][1])
            window.close()
            self.assertEqual(guards.metrics['digest_checks'], 4)
            self.assertEqual(guards.metrics['sampling_windows'], 1)
            with self.assertRaisesRegex(ValueError, 'path changed'):
                supervisor.open_first_fixture_sampling_window(window, active_clients=[active], active=active,
                    out=out / 'other', server_save=server, server_digest=entries[0][1])

    def test_missing_clock_is_rejected_before_starting_any_client(self):
        starts = []
        with self.assertRaisesRegex(ValueError, 'server clock'):
            supervisor.run_overlapping_diagnostics(start=lambda index: starts.append(index), active_clients=[],
                world=object(), host=object(), control=object(), deadline=10, verify=lambda:None,
                measure_first=lambda *_:None)
        self.assertEqual(starts, [])

    def test_window_occurs_after_first_admission_before_second_join(self):
        active=[]; events=[]
        world=SimpleNamespace(session=SimpleNamespace(state='running', pending=None, players=((1,'a'),(2,'b')),
                                                      ready_players=((1,'a'),(2,'b'))))
        control=SimpleNamespace(_peers={})
        def start(index):
            peer=('a','b')[index]
            events.append(('start', peer))
            control._peers[peer] = object()
            players = ((1,'a'),) if index == 0 else ((1,'a'), (2,'b'))
            world.session.players = world.session.ready_players = players
            def finish():
                events.append(('finish', peer))
                return {'client_ticket':{'checkpoint_id':'old'}, 'client_loaded_marker':'a'*32,
                        'server_x4_pid':10, 'server_x4_start_ticks':11,
                        'client_x4_pid':20+index, 'client_x4_start_ticks':21+index}
            return client.ActiveClient(SimpleNamespace(server_tcp=peer), {}, finish,
                                       x4_identity=(20+index, 21+index))
        def tick(_timeout):
            control._peers.pop('a', None)
            world.session.players=world.session.ready_players=((2,'b'),)
        def measure(remaining, clock, tick_owner, check):
            check()
            events.append(('measurement', remaining.x4_identity, len(active)))
            return {'game_time_before':10, 'game_time_after':15}
        checkpoint=SimpleNamespace(checkpoint_id='new',sha256='b'*64,marker='c'*32)
        clock = SimpleNamespace(observe=lambda deadline, tick, check: {'server_game_time_before':15, 'server_game_time_after':16})
        with patch.object(client.recovery.tcp,'await_eof'), \
             patch.object(client,'settle_departure',return_value=checkpoint):
            result=supervisor.run_overlapping_diagnostics(start=start, active_clients=active,
                world=world, host=SimpleNamespace(tick=tick), control=control,
                deadline=time.monotonic()+2, verify=lambda:None, clock=clock, measure_first=measure)
        self.assertEqual(events, [('start','a'), ('measurement',(20,21),1), ('start','b'), ('finish','a'), ('finish','b')])
        self.assertEqual(result['diagnostic_remaining_server_clock']['server_game_time_after'],16)
        self.assertEqual(result['diagnostic_process_measurement']['game_time_before'],10)


if __name__ == '__main__': unittest.main()
