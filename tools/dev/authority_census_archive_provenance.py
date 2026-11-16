#!/usr/bin/env python3
"""Verify one recorded census checkpoint's saved registry; never starts X4."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.checkpoints import CheckpointStore
from authority.marker_evidence import verify_saved_marker
from authority_sector_archive_provenance import _pointer
import authority_registry_save_evidence as registry

# These identify one archived test, not an authenticated production world.
CHECKPOINT_ID = 'checkpoint-a6728d9b21ff4a29b3ab8bf5c912a065'
SHA256 = '64a233ac6a85194b8276212709e78a6c48bbcc0f73c19842622aa098f1408cb8'
SIZE = 25492852
MARKER = '91abdade640301eb5c5e24959f582a72'
REGISTRY_EPOCH = '1370cf1518f8138f3c7e8620917dc1d3'
COUNT = 10054
DEFAULT_STORE = ROOT / '.local/authority-registry-census-01/checkpoints'


def saved_state_script(name):
    """Select the exact save-era scripts for this pinned census checkpoint."""
    if name == 'authority_ship_registry.xml':
        return ROOT / 'tools/dev/fixtures/census-20261115/authority_ship_registry.xml'
    if name in ('authority_checkpoint_marker.xml', 'authority_identity_fixture.xml'):
        return ROOT / 'tools/dev' / name
    raise ValueError('unexpected saved-state script')


def fingerprints(store):
    """Sample archive identities and reject symlinks, including ancestors."""
    store = Path(os.path.abspath(store))
    generation = store / CHECKPOINT_ID
    files = (store / 'CURRENT', store / 'CONFIRMED', generation / 'manifest.json', generation / 'save.xml.gz')
    paths = set(files)
    for path in files:
        paths.update(path.parents)
    result = {}
    for path in paths:
        st = path.lstat()
        if stat.S_ISLNK(st.st_mode):
            raise ValueError('symlink in archive path')
        if path in files:
            if not stat.S_ISREG(st.st_mode): raise ValueError('archive evidence is not a regular file')
        elif not stat.S_ISDIR(st.st_mode):
            raise ValueError('archive ancestor is not a directory')
        identity = (st.st_dev, st.st_ino, st.st_mode)
        if path in files or path in (store, generation):
            identity += (st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        result[str(path)] = identity
    return result


def verify(store_path=DEFAULT_STORE):
    """Check saved marker and complete registry bijection in pinned saved bytes."""
    store_path = Path(os.path.abspath(store_path))
    before = fingerprints(store_path)
    if _pointer(store_path / 'CURRENT') != _pointer(store_path / 'CONFIRMED'):
        raise ValueError('current checkpoint is not confirmed')
    checkpoint = CheckpointStore(store_path).latest_confirmed()
    if (checkpoint.checkpoint_id, checkpoint.sha256, checkpoint.size, checkpoint.path) != (
            CHECKPOINT_ID, SHA256, SIZE, store_path / CHECKPOINT_ID / 'save.xml.gz'):
        raise ValueError('confirmed census checkpoint differs from recorded candidate')
    if verify_saved_marker(checkpoint, MARKER, script_name='X4AuthorityCheckpointMarker', cue_name='Store') is not True:
        raise ValueError('saved marker not verified')
    evidence = registry.verify(checkpoint, REGISTRY_EPOCH, COUNT)
    if (evidence.get('count') != COUNT or evidence.get('unique_saved_components') != COUNT
            or evidence.get('forward_reverse_match') is not True
            or evidence.get('runtime_binding_proven') is not False
            or evidence.get('universe_coverage_proven') is not False):
        raise ValueError('registry evidence does not establish the expected result')
    if fingerprints(store_path) != before:
        raise ValueError('archive changed during verification')
    return {'scope': 'one recorded checkpoint; saved bytes only', 'checkpoint_id': CHECKPOINT_ID,
            'sha256': SHA256, 'size': SIZE, 'registry_epoch': REGISTRY_EPOCH,
            'current_equals_confirmed': True, 'saved_marker_matches': True,
            'registry_entries': COUNT, 'unique_saved_ship_components': COUNT,
            'forward_reverse_match': True, 'runtime_binding_proven': False,
            'exact_loaded_file_proven': False, 'universe_coverage_proven': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, default=DEFAULT_STORE)
    try:
        result = verify(parser.parse_args().store)
    except (OSError, ValueError) as error:
        parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
