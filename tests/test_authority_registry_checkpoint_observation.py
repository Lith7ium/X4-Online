"""Synthetic log evidence for the generated registry bridge verifier."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
from authority_registry_checkpoint_install import verify_bridge_observation

NONCE = 'a' * 32
OTHER_NONCE = 'b' * 32
INITIAL = 'c' * 32
FIRST = 'd' * 32
SECOND = 'e' * 32
COUNT = 130


def evidence(run_id, binding, operational):
    return {'format': 3, 'source_registry_checked': True, 'run_id': run_id,
            'issued_count': COUNT, 'availability_bits': binding,
            'operational_bits': operational, 'available_count': binding.count('1'),
            'unavailable_count': binding.count('0'), 'operational_count': operational.count('1')}


def exchange(nonce, saved, previous=None, first_source=None):
    assert not (previous and first_source)
    capture = previous is not None or first_source is not None
    run_id = saved['run_id']
    binding, operational = saved['availability_bits'], saved['operational_bits']
    rows = []
    if capture:
        action = 'Initialize' if first_source else 'BeginNext'
        rows.append(f'RESPONSE|{nonce}-1|{run_id}|{action}|Initialized|{COUNT}')
    available = unavailable = ops = 0
    for sequence, first in enumerate(range(1, COUNT + 1, 64), 1):
        bits = binding[first - 1:first + 63]
        op_bits = operational[first - 1:first + 63]
        request = f'{nonce}-{sequence + int(capture)}'
        if capture:
            available += bits.count('1')
            unavailable += bits.count('0')
            ops += op_bits.count('1')
            rows.append(f'RESPONSE|{request}|{run_id}|Capture|{first}|{len(bits)}|Captured|'
                        f'{available}|{unavailable}|{ops}|{bits}|{op_bits}')
        else:
            rows.append(f'RESPONSE|{request}|{run_id}|Inspect|{first}|{len(bits)}|Inspected|'
                        f'{bits}|{bits}|{op_bits}|{op_bits}')
    if capture:
        rows.append(f'RESPONSE|{nonce}-5|{run_id}|Seal|Sealed|{COUNT}|'
                    f'{saved["available_count"]}|{saved["unavailable_count"]}|{saved["operational_count"]}')
    mode = 'first_capture' if first_source else 'capture' if capture else 'inspect'
    predecessor = first_source or previous
    rows.append(f'COMPLETE|{mode}|{run_id}|'
                + (f'{predecessor}|' if predecessor else '')
                + f'{COUNT}|{saved["available_count"]}|{saved["unavailable_count"]}|{saved["operational_count"]}')
    return [f'2026-11-20 00:00:00 [X4LAN] AUTH_REGISTRY_CHECKPOINT {nonce}|{row}'
            for row in rows]


class BridgeObservationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.log = Path(temporary.name) / 'engine-output.log'
        self.initial = evidence(INITIAL, '1' * 129 + '0', '1' * 128 + '00')
        self.first = evidence(FIRST, '1' * 128 + '00', '1' * 127 + '000')
        self.second = evidence(SECOND, '1' * 127 + '000', '1' * 126 + '0000')
        self.rows = (exchange(NONCE, self.initial)
                     + exchange(NONCE, self.first, INITIAL)
                     + exchange(NONCE, self.second, FIRST))

    def write(self, rows):
        self.log.write_text('\n'.join(rows) + '\n')

    def test_multiple_runs_correlate_each_saved_snapshot(self):
        self.write(['unrelated engine line', *self.rows, *exchange(OTHER_NONCE, self.second, FIRST)])
        self.assertTrue(verify_bridge_observation(self.log, NONCE, self.initial))
        self.assertTrue(verify_bridge_observation(self.log, NONCE, self.first, previous_run_id=INITIAL))
        self.assertTrue(verify_bridge_observation(self.log, NONCE, self.second, previous_run_id=FIRST))

    def test_refuses_missing_reordered_duplicated_or_foreign_receipts(self):
        cases = {
            'missing': self.rows[:-1],
            'duplicated': [*self.rows, self.rows[-1]],
            'interleaved': [*self.rows[:-2], self.rows[0], *self.rows[-2:]],
            'wrong predecessor': [*self.rows[:-1], self.rows[-1].replace(FIRST, INITIAL)],
            'wrong batch bits': [row[:-2] + '01' if f'|{SECOND}|Capture|129|2|' in row
                                 else row for row in self.rows],
            'nonce error': [*self.rows, f'[X4LAN] AUTH_REGISTRY_CHECKPOINT {NONCE}|ERROR|fault'],
        }
        for name, rows in cases.items():
            with self.subTest(name=name):
                self.write(rows)
                with self.assertRaises(ValueError):
                    verify_bridge_observation(self.log, NONCE, self.second, previous_run_id=FIRST)

    def test_requires_verified_saved_evidence_and_bounded_log(self):
        self.write(self.rows)
        with self.assertRaises(ValueError):
            verify_bridge_observation(self.log, NONCE, {**self.second, 'source_registry_checked': False},
                                      previous_run_id=FIRST)
        with self.assertRaises(ValueError):
            verify_bridge_observation(self.log, NONCE, {**self.second, 'available_count': 130},
                                      previous_run_id=FIRST)
        self.log.write_bytes(b'X' * (16 * 1024 * 1024 + 1))
        with self.assertRaises(ValueError):
            verify_bridge_observation(self.log, NONCE, self.second, previous_run_id=FIRST)

    def test_first_initialize_is_distinct_from_inspect_and_begin_next(self):
        self.write(exchange(NONCE, self.first, first_source=INITIAL)
                   + exchange(NONCE, self.second, previous=FIRST))
        self.assertTrue(verify_bridge_observation(
            self.log, NONCE, self.first, first_capture_source_marker=INITIAL))
        self.assertTrue(verify_bridge_observation(
            self.log, NONCE, self.second, previous_run_id=FIRST))
        for mode in ({}, {'previous_run_id': INITIAL},
                     {'first_capture_source_marker': SECOND},
                     {'first_capture_source_marker': NONCE}):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                verify_bridge_observation(self.log, NONCE, self.first, **mode)
        rows = exchange(NONCE, self.first, first_source=INITIAL)
        rows[0] = rows[0].replace('|Initialize|', '|BeginNext|')
        self.write(rows)
        with self.assertRaises(ValueError):
            verify_bridge_observation(self.log, NONCE, self.first,
                                      first_capture_source_marker=INITIAL)


if __name__ == '__main__':
    unittest.main()
