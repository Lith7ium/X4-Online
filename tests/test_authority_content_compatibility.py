"""Pure manifest comparisons; these tests do not inspect a game or OS."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.content_compatibility import SUPPORTED_SCRIPT_SCHEME, compare


def manifest():
    return {'schema': 1, 'game_version': '900', 'game_build': '23660954',
            'extensions': [{'id': 'ego_dlc_boron', 'version': '900'},
                           {'id': 'x4_lan_lab', 'version': '1'}],
            'scripts': {'scheme': SUPPORTED_SCRIPT_SCHEME, 'sha256': 'a' * 64}}


class ContentCompatibilityTests(unittest.TestCase):
    def test_same_content_ignores_order_and_platform_executables(self):
        host, client = manifest(), manifest()
        host.update(platform='linux', executable_sha256='b' * 64)
        client.update(platform='windows', executable_sha256='c' * 64)
        client['extensions'].reverse()
        before = deepcopy((host, client))
        with patch('builtins.open', side_effect=AssertionError('unexpected I/O')):
            result = compare(host, client)
        self.assertEqual((result.status, result.reasons), ('equal', ()))
        self.assertEqual((host, client), before)

    def test_concrete_build_script_and_extension_differences(self):
        host, client = manifest(), manifest()
        client['game_version'] = '901'; client['game_build'] = '123'
        client['scripts']['sha256'] = 'b' * 64
        client['extensions'] = [{'id': 'x4_lan_lab', 'version': '2'},
                                {'id': 'ego_dlc_terran', 'version': '900'}]
        result = compare(host, client)
        self.assertEqual(result.status, 'different')
        self.assertEqual(set(result.reasons), {
            'game version differs', 'game build differs', 'shared script digest differs',
            'client missing active extension: ego_dlc_boron',
            'client has extra active extension: ego_dlc_terran',
            'active extension version differs: x4_lan_lab'})

    def test_unknown_missing_or_ambiguous_is_unconfirmed(self):
        changes = [lambda x: x.pop('game_build'), lambda x: x.pop('extensions'),
                   lambda x: x.update(extensions=None), lambda x: x.update(schema=True),
                   lambda x: x['extensions'].append(dict(x['extensions'][0])),
                   lambda x: x['scripts'].update(scheme='unknown-v2'),
                   lambda x: x['scripts'].update(sha256='unknown'),
                   lambda x: x.update(game_version='09'),
                   lambda x: x.update(platform='unknown'),
                   lambda x: x.update(executable_sha256='unknown'),
                   lambda x: x.update(unexpected='field')]
        for change in changes:
            with self.subTest(change=change):
                item = manifest(); change(item)
                result = compare(manifest(), item)
                self.assertEqual(result.status, 'unconfirmed')
                self.assertTrue(result.reasons)

    def test_unconfirmed_takes_precedence_over_known_difference(self):
        host, client = manifest(), manifest()
        host['game_build'] = '123'; client.pop('scripts')
        self.assertEqual(compare(host, client).status, 'unconfirmed')

    def test_explicit_empty_extensions_are_not_missing(self):
        host, client = manifest(), manifest()
        host['extensions'] = []; client['extensions'] = []
        self.assertEqual(compare(host, client).status, 'equal')


if __name__ == '__main__':
    unittest.main()
