"""In-memory position authority for an experimental cooperative X4 session.

The registry does not simulate X4, authenticate peers, or apply state to a game.
Callers must serialize access, authenticate the connection, and supply its actual
owner identity (never trust an owner supplied by the remote peer). A unique
world_epoch must be generated for every new registry/session, including restarts.
Positions use an opaque coordinate-frame token; producers and consumers must
agree on its meaning and coordinate units before exchanging game positions.
"""

from dataclasses import dataclass
import math

_MAX_INTEGER = (1 << 63) - 1
_MAX_TOKEN_LENGTH = 256


def _token(value, name):
    if not isinstance(value, str) or not value or len(value) > _MAX_TOKEN_LENGTH:
        raise ValueError(f"{name} must be a nonempty string of at most {_MAX_TOKEN_LENGTH} characters")
    return value


def _integer(value, name, minimum=0):
    if type(value) is not int or not minimum <= value <= _MAX_INTEGER:
        raise ValueError(f"{name} must be an integer from {minimum} to {_MAX_INTEGER}")
    return value


def _owner(value):
    return None if value is None else _token(value, "owner")


def _coordinate(value):
    if type(value) not in (int, float):
        raise ValueError("coordinates must be finite numbers")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("coordinates must be finite numbers") from exc
    if not math.isfinite(number):
        raise ValueError("coordinates must be finite numbers")
    return number


@dataclass(frozen=True)
class Position:
    """Coordinates in a caller-defined frame; the token is not necessarily an X4 sector."""

    sector: str
    x: float
    y: float
    z: float

    def __post_init__(self):
        _token(self.sector, "sector")
        for name in ("x", "y", "z"):
            object.__setattr__(self, name, _coordinate(getattr(self, name)))


@dataclass(frozen=True)
class ShipState:
    """One complete current state; owner None means server low attention."""

    world_epoch: str
    ship_id: str
    generation: int
    authority_epoch: int
    owner: str | None
    sequence: int
    position: Position


class ShipRegistry:
    """Single-threaded, bounded registry with retained per-identity tombstones.

    A ship's generation must increase on recreation, even after removal. A
    transition between server and client or between clients advances its
    authority epoch and starts a new sequence domain. On disconnect the caller
    must explicitly transfer all that client's ships back to the server.
    """

    def __init__(self, world_epoch, *, max_known_ships=100_000):
        self._world_epoch = _token(world_epoch, "world_epoch")
        self._max_known_ships = _integer(max_known_ships, "max_known_ships", 1)
        self._ships = {}
        self._generations = {}

    @property
    def world_epoch(self):
        return self._world_epoch

    def create(self, ship_id, generation, position):
        """Create a server-owned ship with a generation never used for this ID."""
        _token(ship_id, "ship_id")
        _integer(generation, "generation", 1)
        self._check_position(position)
        if ship_id in self._ships:
            raise ValueError("ship already exists")
        previous = self._generations.get(ship_id, 0)
        if generation <= previous:
            raise ValueError("generation must increase after removal")
        if not previous and len(self._generations) >= self._max_known_ships:
            raise ValueError("known ship limit reached")
        state = ShipState(self._world_epoch, ship_id, generation, 1, None, 0, position)
        self._generations[ship_id] = generation
        self._ships[ship_id] = state
        return state

    def _current(self, ship_id, generation, authority_epoch):
        _token(ship_id, "ship_id")
        _integer(generation, "generation", 1)
        _integer(authority_epoch, "authority_epoch", 1)
        state = self._ships.get(ship_id)
        if state is None or state.generation != generation or state.authority_epoch != authority_epoch:
            raise ValueError("unknown or stale ship generation or authority epoch")
        return state

    @staticmethod
    def _check_position(position):
        if not isinstance(position, Position):
            raise ValueError("position must be a Position")

    def assign(self, ship_id, generation, authority_epoch, owner):
        """Transfer authority; repeat assignment to the same owner is a no-op."""
        state = self._current(ship_id, generation, authority_epoch)
        _owner(owner)
        if owner == state.owner:
            return state
        if state.authority_epoch == _MAX_INTEGER:
            raise ValueError("authority epoch exhausted")
        updated = ShipState(self._world_epoch, ship_id, generation,
                            authority_epoch + 1, owner, 0, state.position)
        self._ships[ship_id] = updated
        return updated

    def update(self, world_epoch, ship_id, generation, authority_epoch, owner, sequence, position):
        """Accept a newer full position from the current authenticated owner.

        Updates can skip sequence numbers, but duplicates and reordered older
        messages are rejected. Identity is supplied by the trusted caller.
        """
        if _token(world_epoch, "world_epoch") != self._world_epoch:
            raise ValueError("wrong world epoch")
        state = self._current(ship_id, generation, authority_epoch)
        _owner(owner)
        _integer(sequence, "sequence", 1)
        self._check_position(position)
        if owner != state.owner:
            raise ValueError("sender does not own this ship")
        if sequence <= state.sequence:
            raise ValueError("sequence is not newer")
        updated = ShipState(self._world_epoch, ship_id, generation,
                            authority_epoch, owner, sequence, position)
        self._ships[ship_id] = updated
        return updated

    def remove(self, ship_id, generation, authority_epoch):
        """Remove a current ship and retain its generation as a tombstone."""
        state = self._current(ship_id, generation, authority_epoch)
        del self._ships[ship_id]
        return state

    def snapshot(self):
        """Return a stable, immutable, ship-ID-sorted view of all live ships."""
        return tuple(self._ships[ship_id] for ship_id in sorted(self._ships))
