"""Bounded one-process diagnostic lifecycle; no process or socket on import.

The caller supplies the isolated X4 bridge, a serialized local host channel,
process identity checks and owned-process cleanup. This module does not itself
construct an X4 namespace or claim a working native host transport.
"""
import math
import re
import time

MAX_EVENTS = 4096


def _valid_summary(row, records):
    if not isinstance(row, dict) or set(row) != {
        'observed', 'acknowledged', 'baseline_count', 'classification',
        'birth_confirmed', 'delivery_confirmed', 'coverage'
    }:
        raise ValueError('invalid host summary')
    observed, acknowledged, baseline = (row[k] for k in ('observed', 'acknowledged', 'baseline_count'))
    if (any(type(v) is not int or v < 0 for v in (observed, acknowledged, baseline))
            or baseline > 64 or observed != acknowledged or acknowledged != len(records)
            or row['classification'] != ('inconclusive_no_events' if observed == 0 else 'local_activations_observed')
            or row['birth_confirmed'] is not False or row['delivery_confirmed'] is not False
            or row['coverage'] != 'unknown'):
        raise ValueError('inconsistent host summary')
    seen = set()
    allocated = baseline
    for event in records:
        index, classification = event['index'], event['classification']
        if classification == 'new_registry_entry':
            if index in seen or index != allocated + 1:
                raise ValueError('inconsistent new registry index')
            allocated = index
        elif classification == 'previously_unobserved_existing_index':
            if index in seen or index > baseline:
                raise ValueError('inconsistent previously unobserved index')
        elif index not in seen and index > baseline:
            raise ValueError('unexplained previously observed index')
        seen.add(index)
    return dict(row)


def supervise(*, bridge, channel, check_owner, cleanup, epoch, timeout, bridge_timeout, clock=time.monotonic):
    """Pause, resume, observe, pause, then stop the exclusively owned process.

    Bridge methods must return only after native confirmed receipts. Channel
    start sends one request and receive(timeout) returns one ordered record:
    ('event', dict), ('done', dict), or raises on timeout/fault. `check_owner`
    verifies the originally fenced game and Steam identities. `cleanup` must
    stop only the owned process and return True if none remain. There is no
    retry: an uncertain command or cleanup result invalidates the observation.
    """
    last = deadline = None
    records = []
    paused = False
    error = None
    result = None

    def check(reserve=0):
        nonlocal last
        now = clock()
        if not math.isfinite(now) or now < last or now >= deadline:
            raise TimeoutError('supervisor clock or deadline failed')
        last = now
        if check_owner() is not True: raise RuntimeError('owned process or Steam identity changed')
        now = clock()
        if not math.isfinite(now) or now < last or now >= deadline or deadline-now <= reserve:
            raise TimeoutError('insufficient deadline for bounded operation')
        last = now
        return deadline - now

    def bridge_call(operation):
        check(bridge_timeout + 1)
        operation()
        check()

    try:
        if (not callable(check_owner) or not callable(cleanup) or not callable(clock)
                or not isinstance(epoch, str) or not re.fullmatch(r'[0-9a-f]{32}', epoch)
                or type(bridge_timeout) not in (int, float) or not math.isfinite(bridge_timeout) or bridge_timeout <= 0
                or type(getattr(bridge, '_timeout', None)) not in (int, float)
                or bridge._timeout != bridge_timeout
                or type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError('bounded supervisor requires valid inputs')
        last = clock()
        if not math.isfinite(last): raise ValueError('invalid monotonic clock')
        deadline = last + timeout
        bridge_call(bridge.pause)
        bridge_call(bridge.resume)
        channel.start(); check()
        while True:
            kind, row = channel.receive(check(bridge_timeout + 1) - bridge_timeout - 1)
            check()
            if kind == 'event':
                if len(records) >= MAX_EVENTS:
                    raise ValueError('event evidence limit reached')
                if (not isinstance(row, dict) or set(row) != {
                    'epoch', 'sequence', 'index', 'classification', 'birth_confirmed', 'delivery_confirmed'
                } or row['epoch'] != epoch or type(row['sequence']) is not int or row['sequence'] != len(records) + 1
                    or type(row['index']) is not int or not 1 <= row['index'] <= 9007199254740991
                    or row['classification'] not in ('previously_observed', 'previously_unobserved_existing_index', 'new_registry_entry')
                    or row['birth_confirmed'] is not False or row['delivery_confirmed'] is not False):
                    raise ValueError('invalid host event')
                records.append(dict(row))
            elif kind == 'done':
                result = _valid_summary(row, records)
                break
            else:
                raise ValueError('unexpected host response')
        bridge_call(bridge.pause); paused = True
    except BaseException as exc:
        error = exc
    finally:
        try:
            if not callable(cleanup) or cleanup() is not True:
                raise RuntimeError('owned process cleanup unconfirmed')
        except BaseException as exc:
            failure = RuntimeError('owned process cleanup failed')
            failure.original_error = error
            raise failure from exc
    if error is not None:
        if not isinstance(error, Exception):
            raise error
        raise RuntimeError('isolated observation failed; process fenced') from error
    if not paused:
        raise RuntimeError('native pause not confirmed')
    result['native_pause_confirmed'] = True
    result['owned_cleanup_confirmed'] = True
    result['checkpoint_requested'] = False
    result['events'] = [{key: row[key] for key in ('sequence', 'index', 'classification')} for row in records]
    return result
