"""Disposable loopback fleet relay and independent per-fixture evidence checks."""
import argparse
import json
import math
import os
import re
import select
import signal

IDS = tuple(f'fixture-{i:02d}' for i in range(1, 13))
WARMUP, GAP, MIN_RECEIVES, MAX_AGE = 90, 120, 3, 2.0
_ENROLL = re.compile(r'AUTHORITY_FLEET_ENROLL tick=(\d+) id=(fixture-\d\d) sector=([0-9a-f]{64})\Z')
_SOURCE = re.compile(r'AUTHORITY_FLEET_SOURCE tick=(\d+) id=(fixture-\d\d) seq=(\d+) time=(\S+) x=(\S+) y=(\S+) z=(\S+)\Z')
_RECEIVE = re.compile(r'AUTHORITY_FLEET_RECEIVE tick=(\d+) id=(fixture-\d\d) request=(\d+) seq=(\d+) time=(\S+) x=(\S+) y=(\S+) z=(\S+)\Z')


def validate(source_lines, guest_lines, ticks):
    result = {'pass': False, 'errors': [], 'fixtures': {},
              'clock': 'linux CLOCK_MONOTONIC', 'max_capture_age_s': MAX_AGE,
              'warmup_tick': WARMUP, 'maximum_gap_ticks': GAP, 'minimum_receives': MIN_RECEIVES}
    try:
        if type(ticks) is not int or ticks < 300:
            raise ValueError('fleet evidence requires at least 300 ticks')
        enrolled = [{}, {}]
        source = {ident: {} for ident in IDS}
        received = {ident: [] for ident in IDS}
        previous = [{ident: (0, 0) for ident in IDS} for _ in range(2)]
        for role, lines in enumerate((source_lines, guest_lines)):
            for line in lines:
                if 'NATIVE_GATE AUTHORITY_FLEET_' not in line:
                    continue
                row = line.split('NATIVE_GATE ', 1)[-1].strip()
                match = _ENROLL.fullmatch(row)
                if match:
                    tick, ident, sector = match.groups(); tick = int(tick)
                    if ident not in source or ident in enrolled[role] or not 30 <= tick <= ticks:
                        raise ValueError('invalid or duplicate fixture enrollment')
                    enrolled[role][ident] = sector
                    continue
                match = (_SOURCE if role == 0 else _RECEIVE).fullmatch(row)
                if not match:
                    raise ValueError('unexpected or failed fleet receipt')
                fields = match.groups()
                tick, ident = int(fields[0]), fields[1]
                request = None if role == 0 else int(fields[2])
                seq = int(fields[2] if role == 0 else fields[3])
                values = tuple(float(v) for v in fields[3 if role == 0 else 4:])
                if (ident not in source or not 30 <= tick <= ticks or not 1 <= seq <= (1 << 53)-1
                        or any(not math.isfinite(v) for v in values) or values[0] < 0):
                    raise ValueError('invalid fleet receipt')
                old_tick, old_seq = previous[role][ident]
                if tick < old_tick or (role == 0 and tick == old_tick) or seq <= old_seq:
                    raise ValueError('non-monotonic per-fixture receipt')
                previous[role][ident] = (tick, seq)
                if role == 0:
                    if seq != old_seq + 1:
                        raise ValueError('missing source sequence')
                    source[ident][seq] = (tick, values)
                else:
                    if request is None or not 1 <= request <= (1 << 53)-1:
                        raise ValueError('invalid guest request')
                    received[ident].append((tick, request, seq, values))
        if set(enrolled[0]) != set(IDS) or enrolled[0] != enrolled[1]:
            raise ValueError('per-fixture sector enrollment mismatch')
        for ident in IDS:
            observed, previous_request, ages = [], 0, []
            for tick, request, seq, values in received[ident]:
                if request <= previous_request:
                    raise ValueError('non-monotonic guest request')
                previous_request = request
                original = source[ident].get(seq)
                if not original or original[1][1:] != values[1:]:
                    raise ValueError('unmatched fixture source sequence or coordinates')
                age = values[0] - original[1][0]
                if not 0 <= age <= MAX_AGE:
                    raise ValueError('fixture capture age outside bound')
                ages.append(age)
                if tick >= WARMUP:
                    observed.append(tick)
            if len(observed) < MIN_RECEIVES:
                raise ValueError('insufficient per-fixture coverage: ' + ident)
            gaps = [observed[0]-WARMUP, *(b-a for a,b in zip(observed, observed[1:])), ticks-observed[-1]]
            if max(gaps) > GAP:
                raise ValueError('per-fixture coverage gap exceeded: ' + ident)
            result['fixtures'][ident] = {'source_count': len(source[ident]), 'receive_count': len(received[ident]),
                                         'maximum_gap_ticks': max(gaps), 'maximum_capture_age_s': max(ages)}
        result['pass'] = True
    except (ValueError, OverflowError) as error:
        result['errors'].append(str(error))
    return result


def daemon(fd):
    from authority.fixture_fleet_udp import FixtureFleetUDP
    with os.fdopen(fd, 'r', encoding='ascii') as channel:
        raw = channel.read(4097)
    if len(raw) > 4096:
        raise ValueError('oversized configuration')
    config = json.loads(raw)
    relay = FixtureFleetUDP(fixtures={ident: 'test-frame' for ident in IDS},
                            source_lease=config['source'], guests={'GUEST1': config['guest']}, max_age_seconds=2)
    alive = [True]
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: alive.__setitem__(0, False))
    try:
        print('AUTHORITY_FLEET_READY port=' + str(relay.address[1]), flush=True)
        while alive[0]:
            if select.select([relay.sock], [], [], .1)[0]:
                relay.poll()
    finally:
        relay.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config-fd', type=int, required=True)
    try:
        daemon(parser.parse_args().config_fd)
    except Exception:
        raise SystemExit('authority fleet process failed') from None
