"""Transport-free load-attempt experiment; never authorizes an X4 client.

The caller exclusively serializes this object, its WorldCoordinator, session,
SaveOffers and underlying file service. Peer labels are caller assertions, not
transport identities. Direct concurrent changes, service re-offers, restarted
sessions reusing an epoch, and hostile callers are outside this experiment.
"""
from dataclasses import dataclass
import secrets

from .load_messages import MAX_INTEGER, Receipt, from_load_offer, matches_offer
from .world import WorldCoordinator


@dataclass(frozen=True)
class TestReceiptObservation:
    """A synthetic receipt matched current in-memory state, nothing more."""
    peer: str
    attempt_id: str
    native_load_proven: bool = False
    authenticated: bool = False
    admitted: bool = False


class ExperimentalLoadSession:
    """One in-memory, explicitly non-admitting experiment per coordinator.

    No transfer, engine execution, trusted confirmation or admission is done.
    Restart means discarding this object and using a fresh coordinator epoch.
    """
    def __init__(self, world):
        if type(world) is not WorldCoordinator:
            raise ValueError('world coordinator required')
        self._world = world
        self._peers = {}
        self._active = {}
        self._used = set()
        self._failed = False

    def _live(self):
        if self._failed:
            raise RuntimeError('experimental load session faulted')

    def attach(self, peer):
        """Join a caller-labelled peer; label has no authentication meaning."""
        self._live()
        if type(peer) is not str or not peer or peer in self._peers:
            raise ValueError('invalid or already attached peer')
        if type(self._world.session._next_connection) is not int or not 1 <= self._world.session._next_connection <= MAX_INTEGER:
            raise ValueError('connection handle exceeds experimental codec limit')
        try:
            handle = self._world.join(peer)
        except BaseException:
            # join() may have installed the player before reconciliation fails.
            self._failed = True
            raise
        self._peers[peer] = handle
        return handle

    def disconnect(self, peer):
        self._live()
        if type(peer) is not str or peer not in self._peers:
            raise ValueError('unknown peer')
        handle = self._peers.pop(peer)
        self._active.pop(peer, None)
        try:
            self._world.disconnect(handle)
        except BaseException:
            self._failed = True
            raise

    def begin(self, peer):
        """Withdraw the prior attempt and create a fresh coordinator offer."""
        self._live()
        if type(peer) is not str or peer not in self._peers:
            raise ValueError('unknown peer')
        offer = None
        try:
            attempt = secrets.token_hex(16)
            if attempt in self._used:
                raise ValueError('attempt ID reused')
            baseline = self._world._baseline
            if baseline is None:
                raise ValueError('no baseline')
            cp = baseline[1]
            # Fail before begin_load or offer publication if this coordinator
            # can represent a value which the narrower wire codec cannot.
            Receipt(self._world.session.world_epoch, self._peers[peer],
                    self._world.session.baseline_id, self._world.session._next_load,
                    attempt, cp.checkpoint_id, cp.sha256, cp.size)
            self._active.pop(peer, None)
            self._used.add(attempt)
            offer = self._world.offer_load(self._peers[peer])
            message = from_load_offer(offer, attempt)
            self._active[peer] = (offer, message)
            return message
        except BaseException:
            # A failure may have invalidated an old attempt or partially
            # published a new one; do not retry this experimental session.
            self._failed = True
            if offer is not None:
                try:
                    self._world._offers.revoke(offer.save)
                except BaseException:
                    pass
            raise

    def observe_test_receipt(self, peer, receipt):
        """Consume a matching synthetic receipt, never mark the peer ready."""
        self._live()
        if type(peer) is not str or peer not in self._peers or type(receipt) is not Receipt:
            raise ValueError('unknown peer or invalid test receipt')
        current = self._active.get(peer)
        if current is None:
            raise ValueError('no current attempt for peer')
        offer, message = current
        handle = self._peers[peer]
        world = self._world
        session = world.session
        baseline = world._baseline
        if (session.state != 'paused' or session.pending is not None or session.save_required
                or (handle, peer) not in session.players
                or any(h == handle for h, _ in session.ready_players)
                or session.world_epoch != message.world_epoch
                or session.baseline_id != message.baseline_id
                or session._loads.get(handle) != (message.load_generation, message.baseline_id)
                or world._load_offers.get(handle) != offer
                or baseline is None or baseline[0] != message.baseline_id
                or baseline[1].checkpoint_id != message.checkpoint_id
                or baseline[1].sha256 != message.sha256 or baseline[1].size != message.size
                or offer.save.name not in world._offers.names
                or not matches_offer(receipt, message)):
            raise ValueError('stale or mismatched test receipt')
        # Check the actual service entry too, not just SaveOffers' owned-name set.
        with world._offers.service.lock:
            entry = world._offers.service.offered.get(offer.save.name)
        if entry != (baseline[1].path, message.size, message.sha256):
            raise ValueError('offer withdrawn or changed')
        self._active.pop(peer)
        try:
            world._offers.revoke(offer.save)
            if world._load_offers.get(handle) != offer:
                raise RuntimeError('coordinator offer changed while consuming')
            del world._load_offers[handle]
        except BaseException:
            self._failed = True
            raise
        return TestReceiptObservation(peer, message.attempt_id)
