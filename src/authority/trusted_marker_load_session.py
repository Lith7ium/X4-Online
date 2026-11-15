"""Opt-in marker-bound load claims from trusted cooperative clients.

No listener, transport authentication, X4 process or save loader is provided.
The caller must exclusively own and serialize the coordinator, its store and
offer service, and bind each opaque connection object to the intended live
transport. A claim is an assertion by that trusted client, not independent
proof of bytes read, a continuous pause, or a consistent game world.
"""
from dataclasses import dataclass
import re
import threading

from .experimental_load_session import ExperimentalLoadSession
from .experimental_client_load import HonestClientLoadClaim
from .load_messages import Offer, Receipt
from .marker_evidence import verify_saved_marker

_MARKER = re.compile(r'[0-9a-f]{32}\Z')


@dataclass(frozen=True)
class MarkerBoundOffer:
    """Offer and expected marker from the same confirmed checkpoint."""
    offer: Offer
    marker: str


@dataclass(frozen=True)
class MarkerLoadOutcome:
    """The coordinator accepted a trusted claim, not a byte-level proof."""
    attempt_id: str
    ready_under_trusted_client_assumption: bool = True
    exact_loaded_bytes_proven: bool = False
    client_authenticated: bool = False


class TrustedMarkerLoadSession:
    """Experimental single-owner adapter; never construct without explicit opt-in.

    Methods serialize this wrapper only. Calls directly into its underlying
    coordinator or offer service, filesystem mutations, and transport identity
    verification remain the exclusive caller's responsibility. A failure after
    a possible mutation faults the wrapper; the owner must fence outstanding
    operations and retire or safely settle the coordinator and offer service.
    """
    def __init__(self, world, *, enabled=False):
        if enabled is not True:
            raise ValueError('trusted marker session requires explicit opt-in')
        self._inner = ExperimentalLoadSession(world)
        self._world = world
        self._lock = threading.Lock()
        self._connections = {}
        self._markers = {}
        self._next_peer = 1
        self._failed = False

    def _live(self):
        if self._failed or self._inner._failed:
            raise RuntimeError('trusted marker session faulted')

    def _peer(self, connection):
        entry = self._connections.get(id(connection))
        if entry is None or entry[0] is not connection:
            raise ValueError('unknown or stale connection context')
        return entry[1]

    def attach(self, connection):
        """Attach one caller-owned, identity-stable live connection context."""
        with self._lock:
            self._live()
            if connection is None or isinstance(connection, (str, bytes, int, float, bool, tuple, frozenset)):
                raise ValueError('opaque connection object required')
            if id(connection) in self._connections:
                raise ValueError('connection already attached')
            peer = 'trusted-marker-' + str(self._next_peer)
            self._next_peer += 1
            try:
                handle = self._inner.attach(peer)
                self._connections[id(connection)] = (connection, peer)
            except BaseException:
                self._failed = True
                raise
            return handle

    def disconnect(self, connection):
        with self._lock:
            self._live()
            peer = self._peer(connection)
            try:
                self._inner.disconnect(peer)
                self._markers.pop(peer, None)
                del self._connections[id(connection)]
            except BaseException:
                self._failed = True
                raise

    def begin(self, connection):
        """Make a fresh offer tied to a confirmed, marker-verified checkpoint."""
        with self._lock:
            self._live()
            peer = self._peer(connection)
            try:
                baseline = self._world._baseline
                checkpoint = self._world._store.latest_marked_confirmed()
                if baseline is None or baseline[1] != checkpoint:
                    raise ValueError('baseline is not the confirmed marked checkpoint')
                if verify_saved_marker(checkpoint, checkpoint.marker,
                        script_name='X4AuthorityCheckpointMarker', cue_name='MarkerState') is not True:
                    raise ValueError('checkpoint marker not verified')
                self._markers.pop(peer, None)
                offer = self._inner.begin(peer)
                if (self._world._baseline != baseline or offer.checkpoint_id != checkpoint.checkpoint_id
                        or offer.sha256 != checkpoint.sha256 or offer.size != checkpoint.size):
                    raise ValueError('checkpoint changed while offering')
                self._markers[peer] = (offer.attempt_id, checkpoint)
                return MarkerBoundOffer(offer, checkpoint.marker)
            except BaseException:
                self._failed = True
                raise

    def accept(self, connection, claim, *, pre_accept=None):
        """Accept one trusted claim; an optional side-effect-free guard runs last.

        The guard runs under this wrapper's lock after checkpoint checks and
        must return exactly True. It must not call back into this wrapper.
        """
        with self._lock:
            self._live()
            peer = self._peer(connection)
            if (type(claim) is not HonestClientLoadClaim or type(claim.receipt) is not Receipt
                    or type(claim.marker) is not str or not _MARKER.fullmatch(claim.marker)
                    or claim.load_event_observed is not True or claim.paused_observed is not True):
                raise ValueError('invalid trusted marker claim')
            offer, message = self._inner._current(peer, claim.receipt)
            bound = self._markers.get(peer)
            if bound is None or bound[0] != message.attempt_id or claim.marker != bound[1].marker:
                raise ValueError('marker does not match current attempt')
            # No mutation has occurred yet. The store's manifest/digest and
            # confirmed pointer must still describe the same checkpoint. The
            # caller owns the store exclusively throughout this operation.
            if self._world._store.latest_marked_confirmed() != bound[1]:
                raise ValueError('confirmed checkpoint changed')
            if pre_accept is not None:
                if not callable(pre_accept) or pre_accept() is not True:
                    raise ValueError('pre-accept guard did not confirm readiness')
            try:
                self._world.mark_loaded_trusting_marker(message.world_epoch, message.connection_handle,
                    message.baseline_id, message.load_generation, message.checkpoint_id, message.sha256,
                    trusted_marker_claim=True)
                del self._inner._active[peer]
                del self._markers[peer]
            except BaseException:
                self._failed = True
                raise
            return MarkerLoadOutcome(message.attempt_id)
