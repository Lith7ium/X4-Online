"""Offline recovery integration with a fake engine; this never starts X4."""
import gzip
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from authority.checkpoints import CheckpointStore
from authority.recovery import stage_confirmed_recovery
from authority.save_transfer import SaveOffers, receive
from authority.world import WorldCoordinator
from lockstep.launcher.joinfiles import FileService


# A fixed marker keeps this fake focused on recovery, not marker uniqueness.
MARKER = 'a' * 32


def fake_save_bytes(tick):
    """Create a small synthetic save with the marker structure used by staging."""
    xml = (
        f'<savegame><tick>{tick}</tick><script><refs type="string">'
        f'<ref id="42" string="{MARKER}"/></refs></script>'
        '<md><script name="X4AuthorityCheckpointMarker"><cue name="MarkerState">'
        '<vars><value name="$marker" type="string" value="42"/>'
        '<value name="$loaded" type="integer"/></vars></cue></script></md></savegame>'
    )
    return gzip.compress(xml.encode('ascii'))


def fake_tick(save_bytes):
    return int(ElementTree.fromstring(gzip.decompress(save_bytes)).findtext('tick'))


class FakeEngine:
    """A deterministic stand-in; loading its tick says nothing about X4 loading."""

    pending_marker = MARKER

    def __init__(self, save_path, tick):
        self.save_path = save_path
        self.tick = tick
        self.paused = False

    def pause(self):
        self.paused = True

    def resume(self):
        if not self.paused:
            raise AssertionError('fake engine was not paused')
        self.paused = False

    def save(self):
        if not self.paused:
            raise AssertionError('fake engine must be paused to save')
        self.save_path.write_bytes(fake_save_bytes(self.tick))
        return self.save_path


class FakeParticipants:
    def pause(self, handles):
        return True

    def resume(self, handles):
        return True


@contextmanager
def file_service():
    service = FileService('a' * 32, slots=(1,)).start()
    try:
        yield service
    finally:
        service.close_and_drain()


def run_step(test, world, operation):
    test.assertEqual(world.session.pending.operation, operation)
    test.assertEqual(world.step().operation, operation)


def confirm_load(world, offer):
    world.mark_loaded(offer.world_epoch, offer.connection_handle, offer.baseline_id,
                      offer.load_generation, offer.save.checkpoint_id, offer.save.sha256,
                      trusted_confirmation=True)


class RestartIntegrationTest(unittest.TestCase):
    def test_confirmed_progress_survives_fresh_store_and_coordinator(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store_path = root / 'store'
            store_path.mkdir()
            store = CheckpointStore(store_path)
            engine = FakeEngine(root / 'before-restart.xml.gz', tick=1)

            with file_service() as service:
                world = WorldCoordinator('world-1', engine, store, SaveOffers(service, store),
                                         participants=FakeParticipants())
                connection = world.join('player')
                run_step(self, world, 'pause')
                run_step(self, world, 'save')
                old_offer = world.offer_load(connection)
                confirm_load(world, old_offer)
                run_step(self, world, 'resume')

                # This explicit mutation stands in for progress during play.
                engine.tick = 42
                world.disconnect(connection)
                run_step(self, world, 'pause')
                run_step(self, world, 'save')
                confirmed = store.latest_marked_confirmed()
                self.assertEqual(fake_tick(confirmed.path.read_bytes()), 42)
                self.assertEqual(world.session.state, 'paused')
                self.assertEqual(world.session.players, ())

            # Simulate an unconfirmed publication after the last safe baseline.
            newer_source = root / 'unconfirmed.xml.gz'
            newer_source.write_bytes(fake_save_bytes(999))
            unconfirmed = store.publish(newer_source, marker=MARKER)
            self.assertNotEqual(unconfirmed.checkpoint_id, confirmed.checkpoint_id)
            self.assertEqual(store.latest(), unconfirmed)
            self.assertEqual(store.latest_confirmed(), confirmed)

            # A new store instance and a private, empty profile represent the
            # filesystem side of restart. No real process or game is loaded.
            restarted_store = CheckpointStore(store_path)
            profile = root / 'recovered-profile'
            profile.mkdir(mode=0o700)
            selected, staged = stage_confirmed_recovery(restarted_store, profile)
            self.assertEqual(selected, confirmed)
            self.assertEqual(staged.read_bytes(), confirmed.path.read_bytes())
            recovered_engine = FakeEngine(root / 'after-restart.xml.gz', fake_tick(staged.read_bytes()))

            with file_service() as service:
                restarted_world = WorldCoordinator('world-2', recovered_engine, restarted_store,
                                                   SaveOffers(service, restarted_store),
                                                   participants=FakeParticipants())
                returning_connection = restarted_world.join('player')
                run_step(self, restarted_world, 'pause')
                run_step(self, restarted_world, 'save')
                new_offer = restarted_world.offer_load(returning_connection)
                downloaded = receive('127.0.0.1', service.port, 'a' * 32, 1, new_offer.save,
                                     root / 'returning-client', retries=0, timeout=3)
                self.assertEqual(fake_tick(downloaded.read_bytes()), 42)

                # Even if all other fields are current, a callback from the old
                # coordinator epoch must not mark this new connection ready.
                with self.assertRaises(ValueError):
                    restarted_world.mark_loaded(old_offer.world_epoch, new_offer.connection_handle,
                        new_offer.baseline_id, new_offer.load_generation, new_offer.save.checkpoint_id,
                        new_offer.save.sha256, trusted_confirmation=True)
                with self.assertRaises(ValueError):
                    confirm_load(restarted_world, old_offer)
                self.assertEqual(restarted_world.session.ready_players, ())
                confirm_load(restarted_world, new_offer)
                run_step(self, restarted_world, 'resume')
                self.assertEqual(restarted_world.session.state, 'running')


if __name__ == '__main__':
    unittest.main()
