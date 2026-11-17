"""Verify a completed disposable fixture checkpoint and its saved MD scripts.

This checks source bytes, not what a later X4 process loads or controls.
"""
import json
from pathlib import Path

from authority.checkpoints import CheckpointStore, _read_regular
import authority_player_fixture_save_live as fixture_save
import authority_player_sector_evidence as fixture_evidence

ROOT = Path(__file__).resolve().parents[2]
SAVED_SCRIPTS = (
    'authority_checkpoint_marker.xml',
    'authority_player_fixture_marker.xml',
    'authority_player_seat_experiment.xml',
    'authority_player_sector_fixture.xml',
    'authority_sector_read_guard.xml',
    'authority_sector_reference_fixture.xml',
    'authority_ship_registry.xml',
)


def verify(store_directory, checkpoint, profile):
    """Return source MD bytes after checking the completed isolated save run."""
    store_directory = Path(store_directory)
    if store_directory.name != 'checkpoints':
        raise ValueError('unsupported fixture checkpoint store')
    origin = store_directory.parent
    result = json.loads(_read_regular(origin / 'result.json', 65536))
    if (not isinstance(result, dict) or result.get('success') is not True or
            result.get('checkpoint_confirmed') is not True or
            result.get('confirmation_attempted') is not True or
            result.get('checkpoint_confirmation_uncertain') is not False or
            result.get('owned_processes_remaining') != []):
        raise ValueError('fixture checkpoint was not cleanly confirmed')
    experiment = result.get('experiment')
    if (not isinstance(experiment, dict) or experiment.get('checkpoint_confirmed') is not True or
            experiment.get('saved_fixture_references_checked') is not True or
            experiment.get('checkpoint_id') != checkpoint.checkpoint_id or
            experiment.get('sha256') != checkpoint.sha256):
        raise ValueError('confirmed checkpoint differs from fixture result')
    store = CheckpointStore(store_directory)
    if store.latest_marked_confirmed() != checkpoint:
        raise ValueError('fixture checkpoint is no longer confirmed')
    checked = fixture_evidence.verify(checkpoint, fixture_save.base.archive.REGISTRY_EPOCH, checkpoint.marker)
    if checked.get('saved_slots_checked') != 2 or checked.get('saved_owner_class_sector_checked') is not True:
        raise ValueError('saved fixture references were not verified')
    source_profile = origin / 'case/home/.config/EgoSoft/X4/45841'
    if _read_regular(source_profile / 'content.xml', 65536) != _read_regular(Path(profile) / 'content.xml', 65536):
        raise ValueError('fixture and private extension configuration differ')
    source_md = origin / 'case/extensions/x4_lan_lab/md'
    historical_registry = fixture_save.historical_registry()
    scripts = {}
    for name in SAVED_SCRIPTS:
        expected = historical_registry if name == 'authority_ship_registry.xml' else ROOT / 'tools/dev' / name
        saved = _read_regular(source_md / name, 1 << 20)
        if saved != _read_regular(expected, 1 << 20):
            raise ValueError('fixture saved-state script differs: ' + name)
        scripts[name] = saved
    return scripts
