"""Validate a confirmed registered-fixture save for one isolated reload test."""
import json
from pathlib import Path

from authority.checkpoints import CheckpointStore, _read_regular
from authority.load_messages import _pairs, _reject_constant
import authority_fixture_checkpoint_source as fixture_source
import authority_player_sector_evidence as fixture_evidence

ROOT = Path(__file__).resolve().parents[2]


def verify_current_confirmed(store_directory):
    """Reject an unconfirmed current checkpoint in a stopped source store."""
    directory = Path(store_directory)
    if _read_regular(directory / 'CURRENT', 4096) != _read_regular(directory / 'CONFIRMED', 4096):
        raise ValueError('fixture current checkpoint is not confirmed')


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
    return _verify_mapping_and_scripts(origin, checkpoint, profile, require_original_sector=True)


def verify_recovered(store_directory, checkpoint, profile):
    """Accept a cleanly stopped fixture supervisor's own confirmed checkpoint.

    The caller owns the source and must ensure its writers have stopped. This is
    local provenance, not authentication or a concurrent-writer fence.
    """
    store_directory = Path(store_directory)
    if store_directory.name != 'checkpoints':
        raise ValueError('unsupported registered fixture store')
    origin = store_directory.parent
    try:
        result = json.loads(_read_regular(origin / 'result.json', 65536).decode('utf-8'),
                            object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('invalid fixture supervisor result') from error
    if (type(result) is not dict or type(result.get('supervisor_version')) is not int or
            result['supervisor_version'] != 1 or result.get('fixture_overlap') is not True or
            type(result.get('fixture_registry_count')) is not int or result['fixture_registry_count'] != 4 or
            result.get('success') is not True or result.get('final_world_state') != 'paused' or
            result.get('owned_processes_remaining') != [] or
            'cleanup_error' in result or 'cleanup_errors' in result or
            result.get('final_checkpoint_id') != checkpoint.checkpoint_id or
            result.get('final_checkpoint_sha256') != checkpoint.sha256):
        raise ValueError('fixture supervisor did not end with this confirmed checkpoint')
    store = CheckpointStore(store_directory)
    if store.latest_marked_confirmed() != checkpoint:
        raise ValueError('registered fixture checkpoint is no longer confirmed')
    verify_current_confirmed(store_directory)
    scripts = _verify_mapping_and_scripts(origin, checkpoint, profile, require_original_sector=False)
    if store.latest_marked_confirmed() != checkpoint:
        raise ValueError('registered fixture checkpoint changed during verification')
    verify_current_confirmed(store_directory)
    return scripts


def _verify_mapping_and_scripts(origin, checkpoint, profile, *, require_original_sector):
    epoch = fixture_source.fixture_save.base.archive.REGISTRY_EPOCH
    options = {'registry_count': 4, 'fixture_indices': (3, 4)}
    if not require_original_sector:
        options['require_original_sector'] = False
    checked = fixture_evidence.verify(checkpoint, epoch, checkpoint.marker, **options)
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
