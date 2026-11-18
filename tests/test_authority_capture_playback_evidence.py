"""Deterministic V3 clock/log correlation, no native process or clock oracle."""
from pathlib import Path
import sys
import os
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev'), str(ROOT/'tests')]
import authority_native_client_playback as native
import authority_paired_playback_evidence as paired
from test_authority_paired_playback_evidence import native_log, source_sample


def capture_sample(sequence):
    value = source_sample(sequence)
    velocity = value.pop('velocity')
    return dict(value, version=3, source_time=77, capture_time=200+sequence*.2,
                real_velocity=velocity)


def clock_row(kind, sequence, local_time, *, latest=26):
    value = capture_sample(latest)
    return (f'[X4LAN] AUTH_CLIENT_CAPTURE_CLOCK version=1 kind={kind} epoch={paired.EPOCH} '
            f'index=1318 render_sequence={sequence} latest_source_time={value["source_time"]} '
            f'latest_capture_time={value["capture_time"]} local_time={local_time}\n').encode()


def capture_log(*, alignment=False, sparse=False):
    lines = native_log().splitlines(keepends=True)
    if sparse:
        lines = [line.replace(b'samples=26', b'samples=3') for line in lines]
        lines[1] = lines[1].replace(b'source_sequence=26', b'source_sequence=3')
    result = b''
    if alignment:
        result += (f'[X4LAN] AUTH_CLIENT_INITIAL_ALIGNMENT version=1 epoch={paired.EPOCH} '
                   'index=1318 source_sequence=1 source_time=77 arrival=8.5 local_time=9 '
                   'before_x=0 before_y=2 before_z=3 target_x=1000 target_y=2 target_z=3 '
                   'actual_x=1000 actual_y=2 actual_z=3 error=0 tolerance=3\n').encode()
        result += clock_row('INITIAL_ALIGNMENT', 1, 9, latest=1)
    for line, kind, sequence, local_time, latest in zip(
            lines, ('INITIAL', 'SUMMARY', 'STOPPED'), (1, 3 if sparse else 26, 26),
            (10, 16, 17), (1, 26, 26)):
        result += line + clock_row(kind, sequence, local_time, latest=latest)
    return result


class CapturePlaybackEvidence(unittest.TestCase):
    def evidence(self, path):
        return paired.PairedPlaybackEvidence(path, guard=lambda: True,
            deadline=time.monotonic()+5, latest=True, sample_version=3)

    def test_game_stall_sparse_receipts_use_capture_and_real_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'log'
            path.write_bytes(capture_log(alignment=True, sparse=True))
            evidence = self.evidence(path)
            for sequence in (1, 3, 26):
                evidence.received(capture_sample(sequence))
            result = evidence.stopped(stopped_guard=lambda: True)
            self.assertEqual(result['acknowledged_sequences'], [1, 3, 26])
            self.assertEqual(result['source_samples'], 3)
            self.assertEqual(result['source_game_elapsed'], 0)
            self.assertAlmostEqual(result['source_capture_elapsed'], 5)
            self.assertEqual(result['clock_basis'], 'capture_time')
            self.assertTrue(result['capture_clocks_correlated'])
            self.assertAlmostEqual(result['target_prediction_error'], 0)
            self.assertEqual(result['initial']['initial_alignment_clock']['capture_clock']['latest_capture_time'], 200.2)

    def test_capture_metadata_cannot_be_missing_duplicated_or_unmatched(self):
        valid = capture_log(alignment=True)
        summary_clock = clock_row('SUMMARY', 26, 16)
        bad_logs = [valid.replace(summary_clock, b''), valid + summary_clock,
                    valid.replace(summary_clock, summary_clock*2),
                    valid.replace(b'kind=SUMMARY', b'kind=INITIAL'),
                    valid.replace(b'render_sequence=26', b'render_sequence=25'),
                    valid.replace(b'latest_capture_time=205.2', b'latest_capture_time=nan'),
                    valid.replace(b'kind=INITIAL_ALIGNMENT', b'kind=INITIAL'),
                    valid + b'[X4LAN] AUTH_CLIENT_CAPTURE_CLOCK\n']
        for data in bad_logs:
            with self.subTest(data=data), self.assertRaises(ValueError):
                native.parse_records(data, sample_version=3)

    def test_trailing_pair_is_pending_then_appended_clock_completes_it(self):
        data = capture_log()
        final_clock = clock_row('STOPPED', 26, 17)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'log'
            path.write_bytes(data[:-len(final_clock)])
            reader = native.PlaybackLog(path, sample_version=3)
            with self.assertRaises(native.PlaybackLogPending):
                reader.read()
            with path.open('ab') as stream:
                stream.write(final_clock)
            self.assertIsNotNone(reader.read()[2]['capture_clock'])

    def test_pending_capture_pair_retains_observed_inode_and_prefix(self):
        data = capture_log()
        pending_data = data[:-len(clock_row('STOPPED', 26, 17))]
        for mutation in ('rewrite', 'truncation', 'replacement', 'append'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'log'
                path.write_bytes(pending_data)
                reader = native.PlaybackLog(path, sample_version=3)
                with self.assertRaises(native.PlaybackLogPending):
                    reader.read()
                self.assertEqual(reader._log_bytes, pending_data)
                if mutation == 'replacement':
                    replacement = Path(directory)/'new'
                    replacement.write_bytes(data)
                    os.replace(replacement, path)
                elif mutation == 'rewrite':
                    path.write_bytes(data.replace(b'x=1000 ', b'x=1001 ', 1))
                elif mutation == 'truncation':
                    path.write_bytes(data.split(b'[X4LAN] AUTH_CLIENT_PLAYBACK SUMMARY')[0])
                else:
                    with path.open('ab') as stream:
                        stream.write(clock_row('STOPPED', 26, 17))
                if mutation == 'append':
                    self.assertIsNotNone(reader.read()[2])
                else:
                    with self.assertRaisesRegex(ValueError, 'replaced|truncated_or_rewritten'):
                        reader.read()

    def test_second_capture_growth_must_preserve_first_observed_identity_and_bytes(self):
        evidence_files = native.registry.recovery.marked.file_evidence
        for version in (1, 3):
            data = native_log() if version == 1 else capture_log()
            initial_prefix = data.splitlines(keepends=True)[0]
            before_fingerprint = (1, 2, len(initial_prefix), 3, 4)
            before = (before_fingerprint, 'unused-digest', initial_prefix)
            for mutation in ('replacement', 'rewrite', 'truncation', 'append'):
                with self.subTest(version=version, mutation=mutation):
                    fingerprint = (1, 99 if mutation == 'replacement' else 2, len(data), 5, 6)
                    partial = data
                    if mutation == 'rewrite':
                        partial = data.replace(b'x=1000 ', b'x=1001 ', 1)
                    elif mutation == 'truncation':
                        partial = initial_prefix[:-1]
                    growing = evidence_files.EvidenceFileGrowing(fingerprint, partial)
                    reader = native.PlaybackLog(Path('unused'), sample_version=version)
                    with patch.object(evidence_files, '_read_regular', side_effect=[before, growing]):
                        if mutation == 'append':
                            with self.assertRaises(native.PlaybackLogPending):
                                reader.read()
                            self.assertEqual(reader._log_bytes, data)
                        else:
                            with self.assertRaisesRegex(ValueError, 'replaced|truncated_or_rewritten'):
                                reader.read()
                            self.assertEqual(reader._log_bytes, initial_prefix)
                        self.assertEqual(reader._log_identity, (1, 2))

    def test_native_matching_but_wrong_source_clocks_fail_ack_correlation(self):
        for original, replacement in ((b'latest_source_time=77', b'latest_source_time=78'),
                                      (b'latest_capture_time=205.2', b'latest_capture_time=205.1')):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'log'
                data = capture_log(sparse=True)
                # Alter only SUMMARY/STOPPED; INITIAL remains correctly correlated.
                boundary = data.index(b'[X4LAN] AUTH_CLIENT_PLAYBACK SUMMARY')
                path.write_bytes(data[:boundary] + data[boundary:].replace(original, replacement))
                evidence = self.evidence(path)
                for sequence in (1, 3, 26):
                    evidence.received(capture_sample(sequence))
                with self.assertRaisesRegex(ValueError, 'capture clocks differ'):
                    evidence.stopped(stopped_guard=lambda: True)

    def test_delayed_readback_clocks_match_earlier_ack_but_not_unacked_or_future_sample(self):
        base = capture_log(sparse=True)
        latest_clock = clock_row('SUMMARY', 3, 16)
        cases = [
            (clock_row('SUMMARY', 3, 16, latest=3), 3, True),
            (clock_row('SUMMARY', 3, 16, latest=4), 3, False),
            (clock_row('SUMMARY', 3, 16, latest=26), 2, False),
            (clock_row('SUMMARY', 3, 16, latest=1), 3, False),
        ]
        for replacement, count, accepted in cases:
            with self.subTest(clock=replacement, count=count), tempfile.TemporaryDirectory() as directory:
                data = base.replace(latest_clock, replacement)
                data = data.replace(b'report=1 samples=3 observations=600',
                                    f'report=1 samples={count} observations=600'.encode())
                path = Path(directory)/'log'
                path.write_bytes(data)
                evidence = self.evidence(path)
                for sequence in (1, 3, 26):
                    evidence.received(capture_sample(sequence))
                if accepted:
                    self.assertTrue(evidence.stopped(stopped_guard=lambda: True)['capture_clocks_correlated'])
                else:
                    with self.assertRaisesRegex(ValueError, 'capture clocks differ'):
                        evidence.stopped(stopped_guard=lambda: True)

    def test_progression_and_constructor_versions_fail_closed(self):
        for version in (True, 2, 0, '3'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                paired.PairedPlaybackEvidence('unused', guard=lambda: True,
                    deadline=time.monotonic()+5, sample_version=version)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'log'
            path.write_bytes(capture_log())
            evidence = self.evidence(path)
            evidence.received(capture_sample(1))
            for value in (capture_sample(2) | {'capture_time': 200.2},
                          capture_sample(2) | {'source_time': 76}, source_sample(2)):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    evidence.received(value)
            self.assertEqual(len(evidence.samples), 1)

    def test_alignment_capture_and_readback_correlate_to_original_first_sample(self):
        base = capture_log(alignment=True)
        cases = [base, base.replace(b'actual_x=1000 ', b'actual_x=1010 '),
                 base.replace(b'tolerance=3', b'tolerance=30'),
                 base.replace(b'target_x=1000 ', b'target_x=1001 '),
                 base.replace(b'latest_capture_time=200.2', b'latest_capture_time=200.3'),
                 base.replace(b'error=0 tolerance=3', b'error=1 tolerance=3'),
                 base.replace(b'arrival=8.5', b'arrival=8'),
                 base.replace(b'arrival=8.5', b'arrival=10'),
                 base.replace(b'local_time=9', b'local_time=11')]
        for index, data in enumerate(cases):
            with self.subTest(case=index), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'log'
                path.write_bytes(data)
                evidence = self.evidence(path)
                if index == 0:
                    self.assertTrue(evidence.received(capture_sample(1)))
                else:
                    with self.assertRaises(ValueError):
                        evidence.received(capture_sample(1))


if __name__ == '__main__':
    unittest.main()
