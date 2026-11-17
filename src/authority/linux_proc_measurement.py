"""Owner-driven CPU/RSS measurement bounded by a running-game clock witness.

The caller must supply a clock callback that rejects paused or untrusted game
receipts, plus the owner loop's normal process/session checks and tick. This
module does not launch X4, change scheduling, or measure renderer frame times.
"""
import math
import time


def measure_running_window(*, enabled, sampler, read_running_game_time, tick, check,
                           duration_seconds, deadline, interval_seconds=1.0,
                           monotonic=time.monotonic, sleep=time.sleep):
    """Sample without blocking the owner loop; return only a completed window.

    ``read_running_game_time`` must return a fresh game-time receipt and itself
    reject a paused game. ``check`` and ``tick`` must raise on an invalid owner
    context; an explicit False also fails. Both game-time receipts must be
    finite and advance. Sampling occurs at most once per interval, with actual
    measured intervals retained; missed intervals are never reconstructed. The
    final sample is taken at the end even when less than one interval has passed.
    Fast owner ticks are rate-limited with a small bounded idle wait.
    """
    numbers = (duration_seconds, deadline, interval_seconds)
    if (enabled is not True or not callable(getattr(sampler, 'sample', None)) or
            not all(callable(value) for value in (read_running_game_time, tick, check, monotonic, sleep)) or
            any(type(value) not in (int, float) or not math.isfinite(value) for value in numbers) or
            duration_seconds < 1 or interval_seconds < 1):
        raise ValueError('invalid opt-in measurement context')

    last_time = None
    def now():
        nonlocal last_time
        value = monotonic()
        if (type(value) not in (int, float) or not math.isfinite(value) or
                (last_time is not None and value < last_time)):
            raise RuntimeError('measurement monotonic clock changed')
        last_time = value
        if value >= deadline:
            raise TimeoutError('measurement deadline expired')
        return value

    def checked(callback):
        now()
        if check() is False:
            raise RuntimeError('measurement owner context changed')
        now()
        value = callback()
        now()
        if check() is False:
            raise RuntimeError('measurement owner context changed')
        now()
        return value

    def game_time():
        value = checked(read_running_game_time)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('invalid running game clock receipt')
        return value

    first_game_time = game_time()
    samples = [checked(sampler.sample)]
    start = now()
    until = start + duration_seconds
    next_sample = start + interval_seconds
    if until >= deadline:
        raise TimeoutError('insufficient time for measurement window')
    while True:
        current = now()
        if current >= next_sample or current >= until:
            samples.append(checked(sampler.sample))
            current = now()
            if current >= until:
                break
            next_sample = current + interval_seconds
        tick_started = now()
        if checked(tick) is False:
            raise RuntimeError('measurement owner tick failed')
        # Some pollers return immediately while a socket stays ready. A small
        # bounded wait prevents this diagnostic from creating a busy loop.
        current = now()
        idle_wait = min(0.01 - (current - tick_started), until - current)
        if idle_wait > 0:
            checked(lambda: sleep(idle_wait))
    last_game_time = game_time()
    if last_game_time <= first_game_time:
        raise ValueError('running game clock did not advance')
    return {'game_time_before': first_game_time, 'game_time_after': last_game_time,
            'requested_duration_seconds': duration_seconds,
            'elapsed_seconds': current - start, 'samples': samples,
            'frame_times_measured': False}
