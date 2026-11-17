"""Offline fixture anchor comparison; these rows are not X4 observations."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import authority_fixture_frame_compare as subject


def observation():
    result = {}
    for slot, fixture in subject.FIXTURE_SECTORS.items():
        positions = ((0, 0, 0), (3000, 0, 0), (0, 4000, 0))
        result[slot] = [
            {'code': code, 'macro': macro, 'owner': owner, 'sector': fixture['sector'], 'position': position}
            for (code, (macro, owner)), position in zip(fixture['stations'].items(), positions)
        ]
    return result


class FixtureFrameCompareTests(unittest.TestCase):
    def test_valid_rows_report_per_sector_without_claiming_native_proof(self):
        first = observation(); second = copy.deepcopy(first)
        second[1][0]['position'] = (0.5, 0, 0)
        result = subject.compare(first, second)
        self.assertEqual([(row['slot'], row['expected_registry_index'], row['station_count']) for row in result['sectors']],
                         [(1, 3, 3), (2, 4, 3)])
        self.assertEqual(result['sectors'][0]['max_station_delta'], 0.5)
        self.assertFalse(result['runtime_observation_proven'])
        self.assertFalse(result['cross_process_identity_proven'])
        self.assertFalse(result['universal_frame_identity_proven'])

    def test_missing_duplicate_and_wrong_candidate_are_rejected(self):
        for change in ('missing', 'duplicate', 'wrong_owner', 'wrong_sector', 'foreign_code'):
            with self.subTest(change=change):
                left, right = observation(), observation()
                if change == 'missing': right[1].pop()
                elif change == 'duplicate': right[1][1] = copy.deepcopy(right[1][0])
                elif change == 'wrong_owner': right[1][0]['owner'] = 'player'
                elif change == 'wrong_sector': right[1][0]['sector'] = subject.FIXTURE_SECTORS[2]['sector']
                else: right[1][0]['code'] = 'FAK-999'
                with self.assertRaises(ValueError): subject.compare(left, right)

    def test_rejects_bad_geometry_and_out_of_tolerance(self):
        for change in ('short', 'collinear', 'drift'):
            with self.subTest(change=change):
                left, right = observation(), observation()
                if change == 'short':
                    for index in (0, 1, 2): right[2][index]['position'] = (index, 0, 0)
                elif change == 'collinear': right[2][2]['position'] = (0, 8000, 0); right[2][1]['position'] = (0, 4000, 0)
                else: right[1][0]['position'] = (1.01, 0, 0)
                with self.assertRaises(ValueError): subject.compare(left, right)

    def test_rejects_nonfinite_and_bad_shape(self):
        for position in ((float('nan'), 0, 0), (float('inf'), 0, 0), (True, 0, 0), (0, 0), (1e10, 0, 0), (10**400, 0, 0)):
            with self.subTest(position=position):
                left, right = observation(), observation(); right[1][0]['position'] = position
                with self.assertRaises(ValueError): subject.compare(left, right)
        with self.assertRaises(ValueError): subject.compare(observation(), observation(), tolerance=True)
        with self.assertRaises(ValueError): subject.compare(observation(), {1: []})


if __name__ == '__main__':
    unittest.main()
