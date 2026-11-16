"""Use the existing join-file transport for an explicitly selected checkpoint.

This transfers bytes only. The caller must coordinate pause, game/build and
extension compatibility, validate the received X4 save, load it in a disposable
profile and receive a real readiness confirmation before resuming the world.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import threading

from lockstep.launcher import joinfiles
from .checkpoints import Checkpoint, CheckpointStore


@dataclass(frozen=True)
class SaveOffer:
    name: str
    sha256: str
    size: int
    checkpoint_id: str

    def __post_init__(self):
        if not isinstance(self.name, str) or not re.fullmatch(r'j[1-9][0-9]{0,6}\.xml\.gz', self.name):
            raise ValueError('invalid save offer name')
        if not isinstance(self.sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', self.sha256):
            raise ValueError('invalid save offer hash')
        if type(self.size) is not int or not 0 < self.size <= 512 * 1024 * 1024:
            raise ValueError('invalid save offer size')
        if not isinstance(self.checkpoint_id, str) or not re.fullmatch(r'checkpoint-[0-9a-f]{32}', self.checkpoint_id):
            raise ValueError('invalid checkpoint identity')


class SaveOffers:
    """Offer immutable stored saves via one privately owned join-file service."""

    def __init__(self, service, store):
        if not isinstance(store, CheckpointStore):
            raise ValueError('a checkpoint store is required')
        self.service = service
        self.store = store
        self.names = set()
        self._lock = threading.RLock()

    def offer(self, checkpoint):
        with self._lock:
            if not isinstance(checkpoint, Checkpoint):
                raise ValueError('a verified checkpoint is required')
            if self.store.get(checkpoint.checkpoint_id) != checkpoint:
                raise ValueError('checkpoint does not match the verified store')
            with self.service.lock:
                next_id = getattr(self.service, '_authority_offer_id', 1)
                while next_id <= 9_999_999 and f'j{next_id}.xml.gz' in self.service.offered:
                    next_id += 1
                if next_id > 9_999_999:
                    raise ValueError('save offer IDs exhausted')
                name = f'j{next_id}.xml.gz'
                self.service._authority_offer_id = next_id + 1
            size, digest = self.service.offer(name, checkpoint.path, checkpoint.sha256)
            if size != checkpoint.size:
                self.service.withdraw(name)
                raise ValueError('stored checkpoint size changed')
            self.names.add(name)
            return SaveOffer(name, digest, size, checkpoint.checkpoint_id)

    def invalidate(self):
        """Withdraw offers and interrupt active transfers; admission fencing still applies."""
        with self._lock:
            self.service.withdraw_many(self.names)
            self.names.clear()

    def revoke(self, offer):
        """Withdraw one owned offer and interrupt active transfers."""
        if not isinstance(offer, SaveOffer):
            raise ValueError('a validated save offer is required')
        with self._lock:
            if offer.name in self.names:
                self.service.withdraw(offer.name)
                self.names.remove(offer.name)


def receive(host, port, token, slot, offer, new_directory, *, retries=5, timeout=60, deadline=None):
    """Receive into a newly created directory owned exclusively by the caller.

    The underlying transport resumes interrupted attempts during this call and
    verifies the announced SHA-256. The caller owns the newly created directory
    even on failure. The parent and new directory must not be modified by other
    processes during the transfer: the reused join-file fetcher can replace an
    output path or follow a concurrently inserted partial-file symlink. The
    caller must verify content compatibility and perform native
    load admission separately; receiving bytes does not establish readiness.
    The optional absolute monotonic deadline bounds socket I/O but cannot
    interrupt DNS resolution or a filesystem call in progress. On failure the
    caller retains the directory, any partial file, and potentially a verified
    target if replace completed as the deadline expired, for inspection/cleanup.
    """
    if not isinstance(offer, SaveOffer):
        raise ValueError('a validated save offer is required')
    directory = Path(new_directory)
    joinfiles._remaining(deadline)
    directory.mkdir(mode=0o700)  # parent must exist; refuse existing paths
    joinfiles._remaining(deadline)
    target = directory / 'save.xml.gz'
    joinfiles.fetch(host, port, token, slot, offer.name, target,
                    expect_sha=offer.sha256, expect_size=offer.size,
                    retries=retries, timeout=timeout, offer_wait_s=0, deadline=deadline)
    joinfiles._remaining(deadline)
    size = target.stat().st_size
    joinfiles._remaining(deadline)
    if size != offer.size:
        raise ValueError('received save size differs from offer')
    return target
