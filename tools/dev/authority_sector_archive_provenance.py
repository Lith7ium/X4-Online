#!/usr/bin/env python3
"""Read-only check of the recorded two-sector diagnostic checkpoint, not an X4 loader."""
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
import authority_sector_reference_evidence as sector_evidence

# Captured independently from this diagnostic's confirmed store and server log.
# These values identify this one archived candidate; they do not authenticate it
# against a malicious local user or establish any runtime load.
CHECKPOINT_ID = 'checkpoint-7d2d777f8a2e4ae5a1821372bff27a53'
SHA256 = '2c6494308424fffe8bd114bd017802e2b6dc1f227a64998aea8a787672846748'
SIZE = 25358471
MARKER = 'd39d62a38e3884b5d777c40e994ee5a9'
REGISTRY_EPOCH = '7b772654183db5766a6e73b38d4ac1e8'
DEFAULT_STORE = ROOT / '.local/authority-sector-reference-01/checkpoints'


def _path_fingerprints(store):
    """Reject symlinks and sample all directory and evidence-file identities."""
    store = Path(os.path.abspath(store))
    folder = store / CHECKPOINT_ID
    files = (store / 'CURRENT', store / 'CONFIRMED', folder / 'manifest.json', folder / 'save.xml.gz')
    paths = set()
    for path in files:
        paths.add(path)
        paths.update(path.parents)
    snapshot = {}
    for path in sorted(paths, key=lambda p: (len(p.parts), str(p))):
        st = path.lstat()
        if stat.S_ISLNK(st.st_mode):
            raise ValueError('symlink in archive path')
        if path in files:
            if not stat.S_ISREG(st.st_mode): raise ValueError('archive evidence is not a regular file')
        elif not stat.S_ISDIR(st.st_mode):
            raise ValueError('archive parent is not a directory')
        identity = (st.st_dev, st.st_ino, st.st_mode)
        # Unrelated writes under /, the workspace or .local must not make an
        # unchanged archive fail. Detect replacement of every ancestor, and
        # content/entry changes in the archive directories and evidence files.
        if path in files or path in (store, folder):
            identity += (st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        snapshot[str(path)] = identity
    return snapshot


def _pointer(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError('pointer is not a regular file')
        data = b''
        while len(data) <= 4096:
            chunk = os.read(fd, 4097 - len(data))
            if not chunk: break
            data += chunk
        if len(data) > 4096: raise ValueError('pointer exceeds size limit')
        return data
    finally:
        os.close(fd)


def verify(store_path=DEFAULT_STORE):
    """Validate the fixed archived candidate without writing, loading or trusting result.json."""
    store_path = Path(os.path.abspath(store_path))
    before = _path_fingerprints(store_path)
    if _pointer(store_path / 'CURRENT') != _pointer(store_path / 'CONFIRMED'):
        raise ValueError('current checkpoint is not the confirmed checkpoint')
    checkpoint = CheckpointStore(store_path).latest_confirmed()
    if (checkpoint.checkpoint_id, checkpoint.sha256, checkpoint.size) != (CHECKPOINT_ID, SHA256, SIZE):
        raise ValueError('confirmed archive checkpoint differs from recorded candidate')
    if checkpoint.path != store_path / CHECKPOINT_ID / 'save.xml.gz':
        raise ValueError('confirmed archive path differs')
    if verify_saved_marker(checkpoint, MARKER, script_name='X4AuthorityCheckpointMarker', cue_name='Store') is not True:
        raise ValueError('saved marker not confirmed')
    checked = sector_evidence.verify(checkpoint, REGISTRY_EPOCH)
    if (checked.get('slots_checked') != 2 or checked.get('saved_ship_sector_ancestry_matches') is not True
            or checked.get('runtime_binding_proven') is not False
            or checked.get('exact_loaded_file_proven') is not False
            or checked.get('universe_coverage_proven') is not False):
        raise ValueError('sector evidence did not establish the expected bounded result')
    after = _path_fingerprints(store_path)
    if after != before:
        changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
        raise ValueError('archive evidence changed during verification: ' + ', '.join(changed))
    return {'scope': 'one recorded confirmed checkpoint; saved bytes only',
            'checkpoint_id': CHECKPOINT_ID, 'sha256': SHA256, 'size': SIZE,
            'registry_epoch': REGISTRY_EPOCH, 'current_equals_confirmed': True, 'saved_marker_matches': True,
            'slots_checked': 2, 'saved_ship_sector_ancestry_matches': True,
            'historical_result_reinterpreted': False, 'runtime_binding_proven': False,
            'exact_loaded_file_proven': False, 'universe_coverage_proven': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, default=DEFAULT_STORE,
                        help='directory containing the fixed recorded confirmed checkpoint')
    try:
        result = verify(parser.parse_args().store)
    except (OSError, ValueError) as error:
        parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
