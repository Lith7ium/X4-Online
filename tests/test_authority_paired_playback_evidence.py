"""Portable native-log fixtures, not a live X4 playback test."""
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_paired_playback_evidence as subject


def source_sample(sequence):
    return dict(version=1, epoch=subject.EPOCH, generation='c'*32, index=1318,
                sequence=sequence, sector_macro=subject.SECTOR, source_time=100+sequence*.2,
                x=1000+(sequence-1)*.8, y=2.0, z=3.0,
                velocity=None if sequence == 1 else dict(x=4.0, y=0.0, z=0.0))


def native_log(*, target=1021.4, uncertain=0, phase='frozen'):
    common = f'version=1 epoch={subject.EPOCH} index=1318 sector={subject.SECTOR}'
    initial = f'INITIAL {common} source_sequence=1 local_time=10 game_time=7 x=1000 y=2 z=3'
    pose = f'actual_x={target} actual_y=2 actual_z=3 target_x={target} target_y=2 target_z=3 error=0'
    summary = f'SUMMARY {common} source_sequence=26 local_time=16 game_time=13 report=1 samples=26 observations=600 readbacks=590 phase={phase} {pose}'
    stopped = f'STOPPED {common} source_sequence=26 local_time=17 game_time=14 report=1 samples=26 observations=620 readbacks=610 phase={phase} {pose} uncertain={uncertain} drained=1'
    return ''.join('[X4LAN] AUTH_CLIENT_PLAYBACK '+line+'\n' for line in (initial, summary, stopped)).encode()


class PairedEvidence(unittest.TestCase):
    def evidence(self, path):
        return subject.PairedPlaybackEvidence(path, guard=lambda: True, deadline=time.monotonic()+5)

    def feed(self, evidence):
        for sequence in range(1, 27):
            sample = source_sample(sequence)
            self.assertTrue(evidence.received(sample))
            sample['x'] = -1
        self.assertEqual(evidence.samples, [source_sample(n) for n in range(1, 27)])

    def test_complete_log_correlates_original_source_and_separate_stopped_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'engine.log'; path.write_bytes(native_log())
            evidence = self.evidence(path); self.feed(evidence)
            evidence.guard = lambda: self.fail('active worker guard used after STOP')
            result = evidence.stopped(stopped_guard=lambda: True)
            self.assertEqual(result['source_samples'], 26)
            self.assertAlmostEqual(result['source_displacement'], 20)
            self.assertAlmostEqual(result['client_displacement'], 21.4)
            self.assertAlmostEqual(result['source_game_elapsed'], 5)
            self.assertAlmostEqual(result['target_prediction_error'], 0)
            self.assertFalse(result['native_velocity_proven'])
            self.assertFalse(result['cross_process_identity_proven'])

    def test_rejects_unconfirmed_stop_wrong_prediction_and_faulted_log(self):
        for log in (native_log(uncertain=1), native_log(target=1020), native_log(phase='held'),
                    native_log()+b'AUTH_RECOVERED_CLIENT_MOTION ERROR reason=playback\n'):
            with self.subTest(log=log[-100:]), tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'engine.log'; initial=log.splitlines(keepends=True)[0]; path.write_bytes(initial)
                evidence=self.evidence(path); self.feed(evidence)
                with path.open('ab') as stream: stream.write(log[len(initial):])
                with self.assertRaises(ValueError): evidence.stopped(stopped_guard=lambda: True)

    def test_source_identity_clock_and_initial_offset_are_not_relabelled(self):
        for mutation in ({'index': 42}, {'sequence': 2}, {'x':1051}, {'sector_macro':'other'}):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'engine.log'; path.write_bytes(native_log())
                evidence=self.evidence(path)
                with self.assertRaises(ValueError): evidence.received(source_sample(1)|mutation)
                self.assertEqual(evidence.samples, [])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'engine.log'; path.write_bytes(native_log())
            evidence=self.evidence(path); evidence.received(source_sample(1))
            for mutation in ({'generation':'d'*32}, {'source_time':100.2}, {'sequence':3}):
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    evidence.received(source_sample(2)|mutation)
            self.assertEqual(len(evidence.samples), 1)
