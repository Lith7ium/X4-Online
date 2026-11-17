"""Validate a confirmed registered-fixture save for one isolated reload test."""
import json
from pathlib import Path

from authority.checkpoints import CheckpointStore, _read_regular
import authority_fixture_checkpoint_source as fixture_source
import authority_player_sector_evidence as fixture_evidence

ROOT = Path(__file__).resolve().parents[2]


def verify(store_directory, checkpoint, profile):
    """Bind the confirmed save, four-entry mapping, result, and saved MD bytes."""
    store_directory = Path(store_directory)
    if store_directory.name != 'checkpoints':
        raise ValueError('unsupported registered fixture store')
    origin = store_directory.parent
    result = json.loads(_read_regular(origin / 'registry-save-result.json', 65536))
    if (type(result) is not dict or result.get('success') is not True or
            result.get('checkpoint_confirmed') is not True or
            result.get('confirmation_attempted') is not True or
            result.get('checkpoint_confirmation_uncertain') is not False or
            result.get('saved_registry_mapping_verified') is not True or
            result.get('owned_processes_remaining') != []):
        raise ValueError('registered fixture checkpoint was not cleanly confirmed')
    experiment = result.get('experiment')
    if (type(experiment) is not dict or experiment.get('checkpoint_confirmed') is not True or
            experiment.get('saved_fixture_registry_mapping_checked') is not True or
            experiment.get('checkpoint_id') != checkpoint.checkpoint_id or
            experiment.get('sha256') != checkpoint.sha256):
        raise ValueError('registered fixture result differs from confirmed checkpoint')
    if CheckpointStore(store_directory).latest_marked_confirmed() != checkpoint:
        raise ValueError('registered fixture checkpoint is no longer confirmed')
    epoch = fixture_source.fixture_save.base.archive.REGISTRY_EPOCH
    checked = fixture_evidence.verify(checkpoint, epoch, checkpoint.marker,
                                      registry_count=4, fixture_indices=(3, 4))
    if (checked.get('saved_slots_checked') != 2 or
            checked.get('saved_owner_class_sector_checked') is not True or
            checked.get('saved_registry_slot_mapping_checked') is not True):
        raise ValueError('registered fixture mapping not verified')
    source_profile = origin / 'case/home/.config/EgoSoft/X4/45841'
    if _read_regular(source_profile / 'content.xml', 65536) != _read_regular(Path(profile) / 'content.xml', 65536):
        raise ValueError('fixture and private extension configuration differ')
    source_md = origin / 'case/extensions/x4_lan_lab/md'
    historical_registry = fixture_source.fixture_save.historical_registry()
    scripts = {}
    for name in fixture_source.SAVED_SCRIPTS:
        expected = historical_registry if name == 'authority_ship_registry.xml' else ROOT / 'tools/dev' / name
        saved = _read_regular(source_md / name, 1 << 20)
        if saved != _read_regular(expected, 1 << 20):
            raise ValueError('registered fixture saved-state script differs: ' + name)
        scripts[name] = saved
    return scripts
