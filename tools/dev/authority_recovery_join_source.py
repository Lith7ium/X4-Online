"""Read-only provenance for the recorded TCP-recovery bridge checkpoint.

These fixed values identify one local experiment, not an authenticated world.
The caller must independently isolate its output and fence source writers.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
from authority.checkpoints import CheckpointStore
from authority.load_messages import _pairs, _reject_constant
from authority.marker_evidence import verify_saved_marker
from authority_marked_admission_evidence import _read_regular
import authority_tcp_recovery_source as prior

DEFAULT_STORE = ROOT/'.local/authority-tcp-recovery-01/checkpoints'
CHECKPOINT_ID = 'checkpoint-cdbae20de21c4a47901061374a196c70'
SHA256 = '36833a68e8549c6b5ca105db3dbcbc183c0a0257aa9b0a30ff212639d2e2f018'
SIZE = 25791661
MARKER = 'c4e0b98e123a273edb2551c96f50681f'


def _files(store):
    origin = store.parent; case = origin/'case'; md = case/'extensions/x4_lan_lab/md'
    return (origin/'result.json', case/'home/.config/EgoSoft/X4/45841/content.xml',
            md/'authority_checkpoint_marker.xml', md/'authority_identity_fixture.xml',
            store/'CURRENT', store/'CONFIRMED', store/CHECKPOINT_ID/'manifest.json',
            store/CHECKPOINT_ID/'save.xml.gz')


def _fingerprints(store):
    files = set(_files(store)); paths = set(files)
    md = store.parent/'case/extensions/x4_lan_lab/md'
    for path in files: paths.update(path.parents)
    result = {}
    for path in paths:
        st = path.lstat()
        if stat.S_ISLNK(st.st_mode): raise ValueError('symlink in source archive path')
        if path in files:
            if not stat.S_ISREG(st.st_mode): raise ValueError('source evidence is not a file')
        elif not stat.S_ISDIR(st.st_mode): raise ValueError('source parent is not a directory')
        identity = (st.st_dev, st.st_ino, st.st_mode)
        if path in files or path in (store, store/CHECKPOINT_ID, md):
            identity += (st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        result[str(path)] = identity
    return result


def verify(store_dir, checkpoint, profile):
    """Return verified archived identity-fixture bytes, without launching X4.

    All path checks are sampled and not an adversarial/ABA-safe directory
    fence. The caller must exclusively own the destination and fence writers.
    Success does not establish exact X4 load bytes or runtime fixture state.
    """
    store = Path(os.path.abspath(store_dir))
    if store != Path(os.path.abspath(DEFAULT_STORE)): raise ValueError('only the recorded recovery source is supported')
    before = _fingerprints(store)
    result_path, source_content, marker_script, fixture, current, confirmed, _, _ = _files(store)
    if {p.name for p in marker_script.parent.iterdir()} != {marker_script.name, fixture.name}:
        raise ValueError('unexpected source saved-state scripts')
    if _read_regular(current, 4096, collect=True)[2] != _read_regular(confirmed, 4096, collect=True)[2]:
        raise ValueError('current checkpoint is not confirmed')
    actual = CheckpointStore(store).latest_marked_confirmed()
    if (actual != checkpoint or (actual.checkpoint_id, actual.sha256, actual.size, actual.marker) !=
            (CHECKPOINT_ID, SHA256, SIZE, MARKER) or actual.path != store/CHECKPOINT_ID/'save.xml.gz'):
        raise ValueError('recorded checkpoint identity differs')
    if verify_saved_marker(actual, MARKER, script_name='X4AuthorityCheckpointMarker', cue_name='MarkerState') is not True:
        raise ValueError('saved checkpoint marker differs')
    raw = _read_regular(result_path, 65536, collect=True)[2]
    try: result = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error: raise ValueError('invalid source result') from error
    flags = ('success','load_marker_observed','pause_observed','bridge_activated','coordinator_paused',
             'source_client_disconnect_simulated','saved_identity_fixture_preserved')
    if (type(result) is not dict or any(result.get(k) is not True for k in flags) or
            result.get('source_type') != 'tcp-last-disconnect' or
            result.get('source_checkpoint_id') != prior.CHECKPOINT_ID or result.get('source_sha256') != prior.SHA256 or
            result.get('fresh_checkpoint_id') != CHECKPOINT_ID or result.get('fresh_sha256') != SHA256 or
            type(result.get('owned_processes_remaining')) is not list or result['owned_processes_remaining'] or
            'cleanup_error' in result or 'cleanup_errors' in result):
        raise ValueError('source recovery experiment did not complete as recorded')
    if _read_regular(source_content, 65536, collect=True)[2] != _read_regular(Path(profile)/'content.xml',65536,collect=True)[2]:
        raise ValueError('source and recovery extension configuration differs')
    marker_bytes = _read_regular(marker_script, 65536, collect=True)[2]
    fixture_bytes = _read_regular(fixture, 65536, collect=True)[2]
    if (hashlib.sha256(marker_bytes).hexdigest() != prior.MARKER_SCRIPT_SHA256 or
            marker_bytes != _read_regular(ROOT/'src/authority/md/checkpoint_marker.xml',65536,collect=True)[2] or
            hashlib.sha256(fixture_bytes).hexdigest() != prior.FIXTURE_SHA256 or
            fixture_bytes != _read_regular(ROOT/'tools/dev/authority_identity_fixture.xml',65536,collect=True)[2]):
        raise ValueError('source saved-state script differs')
    if _fingerprints(store) != before: raise ValueError('source archive changed during verification')
    return fixture_bytes
