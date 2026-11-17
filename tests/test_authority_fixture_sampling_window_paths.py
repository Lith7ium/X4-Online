"""The supervisor pins only saves belonging to the current private clients."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority_recovered_loopback_server import open_fixture_sampling_window


class FixtureSamplingPaths(unittest.TestCase):
    def setUp(self):
        self.out = Path('/private/fixture-test')
        self.suffix = 'client/case/home/.config/EgoSoft/X4/45841/save/save_009.xml.gz'
        self.first = SimpleNamespace(save_target=self.out/'overlap-01'/self.suffix, save_digest='a'*64)
        self.survivor = SimpleNamespace(save_target=self.out/'overlap-02'/self.suffix, save_digest='b'*64)
        self.replacement = SimpleNamespace(save_target=self.out/'overlap-rejoin'/self.suffix, save_digest='c'*64)
        self.server_save = self.out/'server-save'
        self.server_digest = 'd'*64
        self.opened = []
        self.window = SimpleNamespace(open=lambda entries: self.opened.append(entries))

    def open(self, active, selected, directories):
        open_fixture_sampling_window(self.window, active_clients=active, selected_clients=selected,
            directory_names=directories, out=self.out, server_save=self.server_save, server_digest=self.server_digest)

    def test_rejoin_uses_new_client_path_and_digest(self):
        self.open([self.first, self.survivor], (self.first, self.survivor), ('overlap-01', 'overlap-02'))
        self.open([self.survivor, self.replacement], (self.survivor, self.replacement), ('overlap-02', 'overlap-rejoin'))
        self.assertEqual(self.opened[1], [(self.server_save, self.server_digest),
            (self.survivor.save_target, self.survivor.save_digest),
            (self.replacement.save_target, self.replacement.save_digest)])
        self.assertNotIn(self.first.save_target, [path for path, _ in self.opened[1]])

    def test_old_path_wrong_membership_and_mutated_digest_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'save path differs'):
            self.open([self.survivor, self.first], (self.survivor, self.first), ('overlap-02', 'overlap-rejoin'))
        with self.assertRaisesRegex(ValueError, 'clients changed'):
            self.open([self.first, self.survivor], (self.survivor, self.replacement), ('overlap-02', 'overlap-rejoin'))
        self.window.open = lambda entries: setattr(self.replacement, 'save_digest', 'f'*64)
        with self.assertRaisesRegex(ValueError, 'changed while pinning'):
            self.open([self.survivor, self.replacement], (self.survivor, self.replacement), ('overlap-02', 'overlap-rejoin'))


if __name__ == '__main__':
    unittest.main()
