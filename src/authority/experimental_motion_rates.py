"""Experimental single-owner position-rate adapter for ShipRegistry.

This module starts no transport, resolves no X4 actors and writes no game state.
The caller must serialize all registry/adapter access, bind the source to a
trusted authority and supply positions in the same verified coordinate frame.
`source_seconds` must be a monotonic clock in seconds from that authority, with
one continuous clock domain per ship generation and authority epoch. Derived
rates are coordinate units per source second, not native X4 velocity. A fresh
world/session needs a fresh adapter and registry. No clock synchronization,
frame equivalence, playback, collision safety or smoothness is established.
"""
from dataclasses import dataclass
import math

from .ship_state import Position, ShipRegistry, ShipState, Velocity


@dataclass(frozen=True)
class _History:
    generation: int
    authority_epoch: int
    owner: str | None
    last_sequence: int
    last_seconds: float
    frame: str
    reference: Position
    reference_seconds: float
    last_state: ShipState


def _seconds(value):
    if type(value) not in (int, float):
        raise ValueError('source seconds must be a finite number')
    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError('invalid source seconds') from error
    if not math.isfinite(number) or not 0 <= number <= 1e12:
        raise ValueError('invalid source seconds')
    return number


class ExperimentalMotionRates:
    """Feed timestamped complete positions to an existing ShipRegistry.

    Rate history is bounded and per ship. A new generation or authority epoch,
    frame change, first observation, interval outside the configured window, or
    an excessive/nonfinite difference yields velocity=None. Short intervals keep
    the older reference so the next eligible observation can estimate a rate;
    every accepted sample still clears any old rate when no rate is available.
    The supplied owner is an assertion by the trusted caller, not a verified
    network identity. Never mix samples from different physical clocks under one
    generation/authority epoch. Updates from other code in the same lineage
    invalidate this adapter's reference until the caller explicitly forgets it.
    Missing native objects must be fenced by the caller; this class sees only
    position values.
    """
    def __init__(self, registry, *, max_tracks=100_000, min_seconds=0.02,
                 max_seconds=1.0, max_rate=5000.0):
        if type(registry) is not ShipRegistry:
            raise ValueError('an existing ShipRegistry is required')
        if type(max_tracks) is not int or not 1 <= max_tracks <= 1_000_000:
            raise ValueError('invalid track bound')
        values = (min_seconds, max_seconds, max_rate)
        if any(type(value) not in (int, float) for value in values):
            raise ValueError('invalid rate bounds')
        try:
            minimum_interval, maximum_interval, rate_limit = (
                float(value) for value in values
            )
        except OverflowError as error:
            raise ValueError('invalid rate bounds') from error
        if (not all(math.isfinite(value) for value in
                    (minimum_interval, maximum_interval, rate_limit)) or
                not 0 < minimum_interval <= maximum_interval <= 60 or
                not 0 < rate_limit <= 1e9):
            raise ValueError('invalid rate bounds')
        self._registry = registry
        self._max_tracks = max_tracks
        self._min_seconds = minimum_interval
        self._max_seconds = maximum_interval
        self._max_rate = rate_limit
        self._history = {}

    def update(self, world_epoch, ship_id, generation, authority_epoch, owner,
               sequence, position, source_seconds):
        """Apply one newer full position; commit rate history only on success."""
        if type(ship_id) is not str or not 1 <= len(ship_id) <= 256:
            raise ValueError('invalid ship ID')
        if type(sequence) is not int or not 1 <= sequence <= (1 << 63) - 1:
            raise ValueError('invalid sequence')
        if type(position) is not Position:
            raise ValueError('position must be an exact Position')
        now = _seconds(source_seconds)
        previous = self._history.get(ship_id)
        if previous is None and len(self._history) >= self._max_tracks:
            raise ValueError('motion track limit reached')
        same_lineage = previous is not None and (
            previous.generation, previous.authority_epoch, previous.owner
        ) == (generation, authority_epoch, owner)
        if (same_lineage and
                self._registry._current(ship_id, generation, authority_epoch)
                is not previous.last_state):
            raise ValueError('registry changed outside this motion adapter')
        if same_lineage and (sequence <= previous.last_sequence or now < previous.last_seconds):
            raise ValueError('stale sequence or regressed source clock')
        same_frame = same_lineage and previous.frame == position.sector
        rate = None
        reference, reference_seconds = position, now
        if same_frame:
            elapsed_seconds = now - previous.reference_seconds
            if elapsed_seconds < self._min_seconds:
                reference, reference_seconds = previous.reference, previous.reference_seconds
            elif elapsed_seconds <= self._max_seconds:
                rate_x = (position.x - previous.reference.x) / elapsed_seconds
                rate_y = (position.y - previous.reference.y) / elapsed_seconds
                rate_z = (position.z - previous.reference.z) / elapsed_seconds
                components = (rate_x, rate_y, rate_z)
                if (all(math.isfinite(component) for component in components) and
                        math.hypot(*components) <= self._max_rate):
                    rate = Velocity(*components)
        # The registry enforces epoch, actual live generation, authority, owner,
        # and sequence. A rejection cannot advance the estimator's history.
        result = self._registry.update(
            world_epoch, ship_id, generation, authority_epoch, owner, sequence,
            position, rate,
        )
        self._history[ship_id] = _History(
            generation, authority_epoch, owner, sequence, now, position.sector,
            reference, reference_seconds, result,
        )
        return result

    def forget(self, ship_id):
        """Drop only local derivative history; caller owns registry lifetime."""
        if type(ship_id) is not str or not 1 <= len(ship_id) <= 256:
            raise ValueError('invalid ship ID')
        return self._history.pop(ship_id, None) is not None
