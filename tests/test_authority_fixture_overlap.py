"""Offline checks for the opt-in four-entry fixture overlap path."""
from pathlib import Path
import sys
import tempfile
import socket
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev'), str(ROOT / 'tests')]
import authority_fixture_overlap as subject
import authority_player_sector_evidence as fixture_evidence
import test_authority_player_sector_fixture as samples
import test_authority_trusted_marker_load_session as marker_fixture
import test_authority_registered_player_seat as seat_fixture
import authority_registered_player_seat_install as registered_seat
import authority_download_load_live as client_loader
from authority.checkpoints import Checkpoint, CheckpointStore
from authority.local_control_bridge import LocalControlBridge
from authority.save_transfer import SaveOffers
from authority.trusted_marker_load_session import TrustedMarkerLoadSession
from authority.world import WorldCoordinator
import gzip


class FixtureOverlapTest(unittest.TestCase):
    def test_real_client_install_chain_composes_marker_seat_and_private_scripts(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / 'case'
            profile = case / 'home/.config/EgoSoft/X4/45841'; profile.mkdir(parents=True)
            lab = case / 'extensions/x4_lan_lab'; ui, md = lab / 'ui', lab / 'md'
            ui.mkdir(parents=True); md.mkdir(); (lab / 'native').mkdir()
            for path in (ui / 'native_gate_snapshot.lua', md / 'native_gate_battle.xml', ui / 'config.lua'):
                path.write_text('test')
            ticket = dict(world_epoch='a'*32, connection_handle=1, baseline_id=1, load_generation=1,
                          checkpoint_id='checkpoint-'+'b'*32, sha256='c'*64, attempt_id='d'*32, slot='save_009')
            native = Path(directory) / 'native.so'; native.write_bytes(b'private test library')
            participant = subject.FixtureServerClient(time.monotonic()+30, Path(directory), keep_worker=True)
            self.addCleanup(participant.sock.close)
            participant.server_library = native
            client_loader.install_probe(case, profile, ticket)
            participant.install(case)
            protected = participant.protected(case)
            protected += registered_seat.install(case, profile, slot=1, nonce='e'*32,
                epoch='f'*32, timeout=20, scripts=seat_fixture.saved_scripts())
            for path in protected:
                self.assertTrue(path.is_file(), path)
            manifest = (lab / 'ui.xml').read_text()
            self.assertNotIn('authority_identity_probe.lua', manifest)
            self.assertIn('authority_registered_player_control_owner.lua', manifest)
            loader = (ui / 'authority_download_load_probe.lua').read_text()
            self.assertLess(loader.index('X4LAN_AUTHORITY_MARKER_READY()'), loader.index('X4LAN_REGISTERED_PLAYER_CONTROL_TICK()'))
            self.assertIn('X4AuthorityPlayerFixtureMarker', (ui / 'authority_checkpoint_marker_probe.lua').read_text())

    def test_fixture_marker_flows_through_real_save_offer_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'store').mkdir()
            class Engine:
                pending_marker = samples.MARKER
                def pause(self): pass
                def save(self):
                    path = root / 'fixture.gz'
                    path.write_bytes(gzip.compress(samples.document().encode()))
                    return path
                def resume(self): pass
            store = CheckpointStore(root / 'store')
            world = WorldCoordinator('fixture-world', Engine(), store,
                                     SaveOffers(marker_fixture.FakeService(), store))
            session = TrustedMarkerLoadSession(world, enabled=True, marker_script=subject.MARKER_SCRIPT)
            connection = object(); session.attach(connection)
            world.step(); world.step()
            self.assertEqual(session.begin(connection).marker, samples.MARKER)
            with self.assertRaises(ValueError):
                TrustedMarkerLoadSession(world, enabled=True, marker_script='arbitrary-script')

    def test_native_bridge_uses_fixture_marker_before_verify(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            profile = Path(directory) / '45841'; (profile / 'save').mkdir(parents=True)
            sock.bind(('127.0.0.1', 0))
            marker, epoch = 'a'*32, 'b'*32
            cp = Checkpoint('checkpoint-'+'c'*32, profile/'save/save_009.xml.gz', 'd'*64, 10, marker)
            info = SimpleNamespace(checkpoint_id=cp.checkpoint_id, sha256=cp.sha256,
                                   size=cp.size, save_name=f'X4 Authority {epoch} 1')
            bridge = LocalControlBridge(enabled=True, sock=sock, peer=('127.0.0.1', 1234), lease='e'*32,
                world_epoch=epoch, profile=profile, store=SimpleNamespace(get=lambda _: cp),
                verify_checkpoint=lambda *args: info, marker_required=True, marker_script=subject.MARKER_SCRIPT)
            bridge._pending_save = 1; bridge._pending_marker = marker
            with patch('authority.local_control_bridge.verify_saved_marker') as verify, \
                    patch.object(bridge, '_exchange') as exchange:
                self.assertTrue(bridge.checkpoint_published(cp))
                verify.assert_called_once_with(cp, marker, script_name=subject.MARKER_SCRIPT, cue_name='MarkerState')
                exchange.assert_called_once()

    def test_later_checkpoint_allows_new_sector_but_keeps_registry_bijection(self):
        text = samples.registered_document()
        text = text.replace('id="[0x1]"', 'id="[0xff]"', 1)
        text = text.replace('id="[0x2]"', 'id="[0x1]"', 1)
        text = text.replace('id="[0xff]"', 'id="[0x2]"', 1)
        test = samples.FixtureTest()
        with self.assertRaises(fixture_evidence.PlayerFixtureEvidenceError):
            test.check(text, registry_count=2, fixture_indices=(1, 2))
        result = test.check(text, registry_count=2, fixture_indices=(1, 2), require_original_sector=False)
        self.assertTrue(result['saved_registry_slot_mapping_checked'])
        broken = text.replace('<key type="component" value="[0x2]"/><value type="integer" value="2"/>',
                              '<key type="component" value="[0x2]"/><value type="integer" value="1"/>')
        with self.assertRaises(fixture_evidence.registry.RegistryEvidenceError):
            test.check(broken, registry_count=2, fixture_indices=(1, 2), require_original_sector=False)

    def test_private_install_preserves_saved_scripts_and_routes_fixture_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / 'case'; profile = case / 'profile'; profile.mkdir(parents=True)
            lab = case / 'extensions/x4_lan_lab'; ui, md = lab / 'ui', lab / 'md'
            ui.mkdir(parents=True); md.mkdir()
            scripts = {name: ('confirmed:' + name).encode() for name in subject.fixture_source.SAVED_SCRIPTS}
            def install_original(case_arg, profile_arg, port, lease, epoch):
                self.assertEqual((case_arg, profile_arg, port, lease, epoch), (case, profile, 1234, 'l', 'e'))
                for name in ('authority_checkpoint_marker_probe.lua', 'authority_world_bridge_probe.lua'):
                    (ui / name).write_text('X4AuthorityCheckpointMarker.Stored')
                return [ui / 'authority_checkpoint_marker_probe.lua', ui / 'authority_world_bridge_probe.lua']
            with patch.object(subject.bridge, 'install_probe', side_effect=install_original):
                paths = subject.install_server(case, profile, scripts, 1234, 'l', 'e')
            for name, contents in scripts.items():
                self.assertEqual((md / name).read_bytes(), contents)
                self.assertIn(md / name, paths)
            for name in ('authority_checkpoint_marker_probe.lua', 'authority_world_bridge_probe.lua'):
                self.assertIn('X4AuthorityPlayerFixtureMarker.Stored', (ui / name).read_text())
                self.assertNotIn('X4AuthorityCheckpointMarker', (ui / name).read_text())

    def test_client_load_marker_is_ordered_without_old_identity_fixture(self):
        keys = subject.server_client.recovery.base.client.FIELDS
        ticket = dict(zip(keys, ['a'*32, 1, 2, 3, 'checkpoint-'+'b'*32, 'c'*64, 'd'*32, 'save_009']))
        expected = '|'.join(str(ticket[key]) for key in keys)
        marker = 'e'*32
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'engine.log'
            path.write_text('[X4LAN] AUTH_DOWNLOAD_LOAD load_requested|' + expected + '\n'
                            '[X4LAN] AUTH_MARKER load INSPECTED ' + marker + '\n'
                            '[X4LAN] AUTH_DOWNLOAD_LOAD pause_observed|' + expected + '\n')
            subject.check_client_log(path, ticket, marker)
            with path.open('a') as stream:
                stream.write('[X4LAN] AUTH_MARKER load ERROR\n')
            with self.assertRaises(ValueError):
                subject.check_client_log(path, ticket, marker)


if __name__ == '__main__':
    unittest.main()
