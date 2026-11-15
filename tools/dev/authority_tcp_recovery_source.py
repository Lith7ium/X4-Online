"""Read-only provenance for one recorded TCP last-disconnect checkpoint.

Pinned values identify an experiment, not an authenticated production world.
This validates saved bytes and local source artifacts; it does not start X4.
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

DEFAULT_STORE = ROOT/'.local/authority-tcp-last-disconnect-01/checkpoints'
CHECKPOINT_ID = 'checkpoint-5e8e1f852bc84f8b90f6c30c24bd3432'
SHA256 = '71042e25b0d2560f35fbc44fc6f0bcdd688936c153b0d9f7c2fe71fc03cffc1e'
SIZE = 25519997
MARKER = 'be88fd7fdd33362a34818e41daa1ef34'
FIXTURE_SHA256 = '92b515e7f3e47a29762e084ad6d0fe0239e5ba34993c08a63b5c610aeb92dd43'
MARKER_SCRIPT_SHA256 = '6de4be69d19601a02a96e5e7f2285f9d14dfceab9dc9cccb82909b9444625813'


def _files(store):
    origin = store.parent
    server = origin/'server/case'
    return (origin/'result.json', server/'home/.config/EgoSoft/X4/45841/content.xml',
            server/'extensions/x4_lan_lab/md/authority_checkpoint_marker.xml',
            server/'extensions/x4_lan_lab/md/authority_identity_fixture.xml',
            store/'CURRENT', store/'CONFIRMED', store/CHECKPOINT_ID/'manifest.json',
            store/CHECKPOINT_ID/'save.xml.gz')


def _fingerprints(store):
    files = set(_files(store)); paths = set(files)
    md_dir = store.parent/'server/case/extensions/x4_lan_lab/md'
    for path in files: paths.update(path.parents)
    result = {}
    for path in paths:
        st = path.lstat()
        if stat.S_ISLNK(st.st_mode): raise ValueError('symlink in source archive path')
        if path in files:
            if not stat.S_ISREG(st.st_mode): raise ValueError('source evidence is not a file')
        elif not stat.S_ISDIR(st.st_mode): raise ValueError('source parent is not a directory')
        identity = (st.st_dev, st.st_ino, st.st_mode)
        if path in files or path in (store, store/CHECKPOINT_ID, md_dir):
            identity += (st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        result[str(path)] = identity
    return result


def verify(store_dir, checkpoint, profile):
    """Validate the pinned completed run and return its original fixture bytes.

    Snapshots are point-in-time checks. Caller owns the destination and must
    keep the archive unchanged while using it; this is not authentication.
    """
    store = Path(os.path.abspath(store_dir))
    expected_store = Path(os.path.abspath(DEFAULT_STORE))
    if store != expected_store: raise ValueError('only the recorded TCP checkpoint is supported')
    before = _fingerprints(store)
    result_path, source_content, marker_script, fixture, current, confirmed, _, _ = _files(store)
    if {p.name for p in marker_script.parent.iterdir()} != {marker_script.name, fixture.name}:
        raise ValueError('unexpected source saved-state scripts')
    if _read_regular(current, 4096, collect=True)[2] != _read_regular(confirmed, 4096, collect=True)[2]:
        raise ValueError('current checkpoint is not confirmed')
    store_reader = CheckpointStore(store)
    actual = store_reader.latest_marked_confirmed()
    if (actual != checkpoint or (actual.checkpoint_id, actual.sha256, actual.size, actual.marker) !=
            (CHECKPOINT_ID, SHA256, SIZE, MARKER) or actual.path != store/CHECKPOINT_ID/'save.xml.gz'):
        raise ValueError('recorded checkpoint identity differs')
    if verify_saved_marker(actual, MARKER, script_name='X4AuthorityCheckpointMarker', cue_name='MarkerState') is not True:
        raise ValueError('saved checkpoint marker differs')
    raw = _read_regular(result_path, 65536, collect=True)[2]
    try: result = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error: raise ValueError('invalid source result') from error
    flags = ('success','owned_cleanup_confirmed','helper_clean_exit','simulated_client_disconnect',
             'last_eof_observed','last_departure_pause_confirmed','last_departure_checkpoint_confirmed',
             'marker_changed','tcp_claim_used','tcp_participant_commands_used','intermediate_checkpoint_confirmed',
             'remaining_client_resumed','native_server_and_client_resume_confirmed',
             'native_server_and_client_pause_confirmed')
    if (type(result) is not dict or any(result.get(k) is not True for k in flags) or
            type(result.get('owned_processes_remaining')) is not list or result['owned_processes_remaining'] or
            result.get('server_state') != 'paused' or 'pending_operation' not in result or
            result['pending_operation'] is not None or result.get('cleanup_error') or result.get('cleanup_errors') or
            result.get('last_checkpoint_id') != CHECKPOINT_ID or result.get('last_checkpoint_sha256') != SHA256):
        raise ValueError('source TCP experiment did not complete as recorded')
    if _read_regular(source_content, 65536, collect=True)[2] != _read_regular(Path(profile)/'content.xml',65536,collect=True)[2]:
        raise ValueError('source and recovery extension configuration differs')
    marker_bytes = _read_regular(marker_script, 65536, collect=True)[2]
    fixture_bytes = _read_regular(fixture, 65536, collect=True)[2]
    if (hashlib.sha256(marker_bytes).hexdigest() != MARKER_SCRIPT_SHA256 or
            marker_bytes != _read_regular(ROOT/'src/authority/md/checkpoint_marker.xml',65536,collect=True)[2] or
            hashlib.sha256(fixture_bytes).hexdigest() != FIXTURE_SHA256 or
            fixture_bytes != _read_regular(ROOT/'tools/dev/authority_identity_fixture.xml',65536,collect=True)[2]):
        raise ValueError('source saved-state script differs')
    if _fingerprints(store) != before: raise ValueError('source archive changed during verification')
    return fixture_bytes
