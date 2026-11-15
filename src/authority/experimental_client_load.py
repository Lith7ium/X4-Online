"""Opt-in client-side load self-report assembly; no X4 or network calls.

The trusted/cooperative caller supplies local events and exclusively owns the
attempt and staged file. An output is a client assertion, not independent proof
of what X4 read or of the identity or honesty of the client.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat

from .load_messages import Offer, Receipt

_MARKER = re.compile(r'[0-9a-f]{32}\Z')


@dataclass(frozen=True)
class HonestClientLoadClaim:
    """Fields reported by the client; no host-side authentication is implied."""
    receipt: Receipt
    marker: str
    load_event_observed: bool
    paused_observed: bool


def _fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _inspect(path, offer):
    """Hash one staged regular file and reject changes observed while reading."""
    before_path = os.lstat(path)
    if not stat.S_ISREG(before_path.st_mode):
        raise ValueError('staged save is not a regular file')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or _fingerprint(before) != _fingerprint(before_path):
            raise ValueError('staged save changed before reading')
        digest = hashlib.sha256(); size = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk: break
            size += len(chunk)
            if size > offer.size: raise ValueError('staged save too large')
            digest.update(chunk)
        after = os.fstat(fd)
        after_path = os.lstat(path)
        if (_fingerprint(before) != _fingerprint(after) or
                _fingerprint(after) != _fingerprint(after_path) or
                size != offer.size or digest.hexdigest() != offer.sha256):
            raise ValueError('staged save changed or differs from offer')
        return _fingerprint(after), digest.hexdigest()
    finally:
        os.close(fd)


class ExperimentalClientLoad:
    """Assemble one honest-client report from serialized, caller-supplied events.

    `observe_loaded_marker` must only be called after the existing marker cue
    has observed `event_game_loaded` and returned its inspected saved marker.
    `observe_pause` must only be called for the same still-live X4 load attempt
    after an actual pause observation. This class cannot verify those claims.
    """
    def __init__(self, *, enabled, offer, expected_marker):
        if enabled is not True or type(offer) is not Offer:
            raise ValueError('explicitly enabled load offer required')
        if type(expected_marker) is not str or not _MARKER.fullmatch(expected_marker):
            raise ValueError('expected saved marker required')
        self._offer = offer
        self._marker = expected_marker
        self._state = 'new'
        self._path = None
        self._staged = None

    def _expect(self, state, attempt):
        if self._state != state or type(attempt) is not str or attempt != self._offer.attempt_id:
            self._state = 'failed'
            raise ValueError('out-of-order or stale client load event')

    def verify_staged(self, path):
        """Verify staged bytes before the caller requests the load."""
        self._expect('new', self._offer.attempt_id)
        try:
            self._path = Path(path).absolute()
            self._staged = _inspect(self._path, self._offer)
        except BaseException:
            self._state = 'failed'
            raise
        self._state = 'staged'

    def observe_load_requested(self, attempt):
        """Record the caller's load request for this attempt; not completion."""
        self._expect('staged', attempt)
        self._state = 'requested'

    def observe_loaded_marker(self, attempt, marker):
        """Record the marker-cue result supplied by the cooperative caller."""
        self._expect('requested', attempt)
        if type(marker) is not str or marker != self._marker:
            self._state = 'failed'
            raise ValueError('loaded marker differs')
        self._state = 'loaded'

    def observe_pause(self, attempt, paused):
        """Record a pause assertion after the marker-cue observation."""
        self._expect('loaded', attempt)
        if paused is not True:
            self._state = 'failed'
            raise ValueError('pause not observed')
        self._state = 'paused'

    def make_claim(self, attempt):
        """Return one self-reported claim after rechecking staged file bytes."""
        self._expect('paused', attempt)
        try:
            if _inspect(self._path, self._offer) != self._staged:
                raise ValueError('staged save changed during load attempt')
            receipt = Receipt(**{name: getattr(self._offer, name) for name in Receipt.__dataclass_fields__})
            result = HonestClientLoadClaim(receipt, self._marker, True, True)
        except BaseException:
            self._state = 'failed'
            raise
        self._state = 'done'
        return result

    def close(self):
        """Discard this attempt; a new load requires a fresh adapter and offer."""
        self._state = 'closed'
