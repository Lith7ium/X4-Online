"""Read-only evidence for an isolated local marked-load experiment.

A matching marker and local receipts are not proof that X4 read every offered
byte, and are not an authenticated admission. Checks are point-in-time: the
confirmed checkpoint pointer and files can change after their initial check,
including before this function returns. Caller-supplied safety callbacks are
not authenticated. This module starts no process and must not authorize or
perform admission or set trusted_confirmation.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
from collections.abc import Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.marker_evidence import verify_saved_marker
from authority.load_messages import from_load_offer
import authority_checkpoint_marker_live as marker_live
import authority_download_load_live as download_live
import authority_identity_live as identity_live

MAX_LOG = download_live.ReceiptWatch.MAX_LOG
FIELDS = download_live.FIELDS


class EvidenceFileGrowing(ValueError):
    """A regular file grew while captured; its bytes are not a stable snapshot."""
    def __init__(self, fingerprint, partial):
        super().__init__('local evidence file grew while reading')
        self.fingerprint = fingerprint
        self.partial = partial


def _read_regular(path, limit, *, collect):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError('invalid local evidence file')
        digest = hashlib.sha256()
        chunks = []
        total = 0
        while True:
            part = os.read(fd, 1024 * 1024)
            if not part:
                break
            total += len(part)
            if total > limit:
                raise ValueError('local evidence file exceeds limit')
            digest.update(part)
            if collect:
                chunks.append(part)
        after = os.fstat(fd)
        fingerprint = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        if (after.st_size > before.st_size and total >= before.st_size and total <= after.st_size
                and (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)):
            raise EvidenceFileGrowing(fingerprint(before), b''.join(chunks) if collect else None)
        if fingerprint(before) != fingerprint(after) or total != before.st_size:
            raise ValueError('local evidence file changed while reading')
        return (fingerprint(before), digest.hexdigest(), b''.join(chunks) if collect else None)
    finally:
        os.close(fd)


def _check(callback):
    if not callable(callback) or callback() is not True:
        raise ValueError('supervisor safety check failed')


def _current(world, handle, ticket, expected_ticket):
    if type(handle) is not int or not isinstance(ticket, dict) or not isinstance(expected_ticket, Mapping):
        raise ValueError('invalid local attempt')
    if set(ticket) != set(FIELDS) or dict(expected_ticket) != ticket:
        raise ValueError('local attempt differs from supervisor ticket')
    for field in ('connection_handle', 'baseline_id', 'load_generation'):
        if type(ticket[field]) is not int or type(expected_ticket[field]) is not int:
            raise ValueError('invalid local attempt integer')
    for field in ('world_epoch', 'checkpoint_id', 'sha256', 'attempt_id', 'slot'):
        if type(ticket[field]) is not str or type(expected_ticket[field]) is not str:
            raise ValueError('invalid local attempt string')
    if ticket['slot'] != 'save_009' or not isinstance(ticket['attempt_id'], str) or not re.fullmatch(r'[0-9a-f]{32}', ticket['attempt_id']):
        raise ValueError('invalid local attempt')
    offer = world._load_offers.get(handle)
    session = world.session
    if (offer is None or session.state != 'paused' or session.pending is not None or session.save_required
            or not any(h == handle for h, _ in session.players)
            or any(h == handle for h, _ in session.ready_players)):
        raise ValueError('local admission is not pending')
    normalized = from_load_offer(offer, ticket['attempt_id'])
    if (normalized.connection_handle != handle or session.world_epoch != normalized.world_epoch
        or session.baseline_id != normalized.baseline_id
        or session._loads.get(handle) != (normalized.load_generation, normalized.baseline_id) or
        any(getattr(normalized, field) != ticket[field] for field in
            ('world_epoch', 'connection_handle', 'baseline_id', 'load_generation', 'checkpoint_id', 'sha256'))):
        raise ValueError('local attempt differs from current offer')
    return offer, normalized


def _attempt(world, handle, ticket, expected_ticket):
    offer, normalized = _current(world, handle, ticket, expected_ticket)
    checkpoint = world._store.get(normalized.checkpoint_id)
    if (checkpoint.checkpoint_id != normalized.checkpoint_id or checkpoint.sha256 != normalized.sha256 or
            checkpoint.size != normalized.size or world._store.latest_confirmed() != checkpoint
            or world._baseline != (normalized.baseline_id, checkpoint)):
        raise ValueError('checkpoint differs from current offer')
    return offer, checkpoint


def verify(*, world, handle, ticket, expected_ticket, target, marker, server_log, client_log,
           check_processes, check_protected):
    """Describe observed local evidence; the result is not an admission decision."""
    _check(check_processes); _check(check_protected)
    offer, checkpoint = _attempt(world, handle, ticket, expected_ticket)
    if not isinstance(marker, str) or not re.fullmatch(r'[0-9a-f]{32}', marker):
        raise ValueError('invalid marker')
    target_before = _read_regular(target, offer.save.size, collect=False)
    if target_before[0][2] != offer.save.size or target_before[1] != offer.save.sha256:
        raise ValueError('staged checkpoint differs')
    verify_saved_marker(checkpoint, marker, script_name='X4AuthorityCheckpointMarker', cue_name='Store')
    verify_logs(server_log, client_log, marker, ticket)
    _check(check_processes); _check(check_protected)
    if (_current(world, handle, ticket, expected_ticket)[0] != offer or
        world._baseline != (offer.baseline_id, checkpoint) or
        _read_regular(target, offer.save.size, collect=False) != target_before):
        raise ValueError('local evidence changed during verification')
    return {'scope': 'isolated local marked-load evidence', 'staged_bytes_match': True,
            'saved_marker_matches': True, 'ordered_load_receipts': True,
            'exact_x4_bytes_read_proven': False, 'attempt_authenticated': False,
            'confirmed_checkpoint_current_at_return_proven': False,
            'admission_authorized': False, 'client_admitted': False}


def verify_logs(server_log, client_log, marker, ticket):
    """Compare log observations; the result cannot authorize admission."""
    server_before = _read_regular(server_log, MAX_LOG, collect=True)
    client_before = _read_regular(client_log, MAX_LOG, collect=True)
    before = identity_live.observations_bytes(server_before[2], 'save')
    after = identity_live.observations_bytes(client_before[2], 'load')
    if [(x['name'], x['macro']) for x in before] != [(x['name'], x['macro']) for x in after]:
        raise ValueError('fixture observations differ')
    marker_live.verify_receipts(server_before[2].decode('utf-8'), client_before[2].decode('utf-8'), marker, ticket)
    # Parse exactly the same captured bytes used for identity and marker checks.
    # ReceiptWatch.poll() would reopen the path and could read another version.
    watch = download_live.ReceiptWatch(client_log, ticket)
    client_bytes = client_before[2]
    if client_bytes and not client_bytes.endswith(b'\n'):
        raise ValueError('load receipts incomplete')
    stage = 0
    for line in client_bytes.split(b'\n'):
        if len(line) > watch.MAX_LINE:
            raise ValueError('receipt line too long')
        if download_live.TAG not in line:
            continue
        row = line.split(download_live.TAG, 1)[1].strip()
        if stage >= len(watch.expected) or row != watch.expected[stage]:
            raise ValueError('unexpected, duplicate, or mismatched receipt')
        stage += 1
    if stage != len(watch.expected):
        raise ValueError('load receipts incomplete')
    # Require precisely one marker between the two ordered receipt lines.
    ordered = []
    for line in client_before[2].splitlines():
        if download_live.TAG in line:
            ordered.append('load')
        if b'AUTH_MARKER ' in line:
            ordered.append('marker')
    if ordered != ['load', 'marker', 'load']:
        raise ValueError('load and marker receipt order invalid')
    if (_read_regular(server_log, MAX_LOG, collect=True) != server_before or
        _read_regular(client_log, MAX_LOG, collect=True) != client_before):
        raise ValueError('local log changed during verification')
