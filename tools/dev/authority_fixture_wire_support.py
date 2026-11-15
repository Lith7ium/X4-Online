"""Local, read-only one-fixture diagnostic daemon and strict receipt validator."""
import argparse
import json
import math
import os
import re
import select
import signal

_MAX_SEQ = (1 << 53) - 1
_SOURCE = re.compile(r'^AUTHORITY_WIRE_SOURCE tick=(\d+) seq=(\d+) x=(\S+) y=(\S+) z=(\S+)$')
_RECEIVE = re.compile(r'^AUTHORITY_WIRE_RECEIVE tick=(\d+) request=(\d+) seq=(\d+) x=(\S+) y=(\S+) z=(\S+)$')


def validate(source_lines, guest_lines, ticks):
    """Check received coordinates against independently logged source sequences."""
    result = {'pass': False, 'source_count': 0, 'receive_count': 0, 'errors': []}
    try:
        source, received = {}, []
        for role, lines in (('source', source_lines), ('guest', guest_lines)):
            previous_seq = previous_request = previous_tick = 0
            for line in lines:
                if 'NATIVE_GATE AUTHORITY_WIRE_' not in line:
                    continue
                row = line.split('NATIVE_GATE ', 1)[-1].strip()
                match = (_SOURCE if role == 'source' else _RECEIVE).fullmatch(row)
                if not match:
                    raise ValueError('unexpected or failed wire receipt')
                parts = match.groups()
                tick = int(parts[0]); request = None if role == 'source' else int(parts[1])
                sequence = int(parts[1] if role == 'source' else parts[2])
                coordinates = tuple(float(v) for v in parts[2 if role == 'source' else 3:])
                if (not 30 <= tick <= ticks or tick <= previous_tick or not 1 <= sequence <= _MAX_SEQ or sequence <= previous_seq
                        or any(not math.isfinite(x) for x in coordinates)):
                    raise ValueError('invalid or non-monotonic wire receipt')
                if role == 'source' and sequence != previous_seq + 1:
                    raise ValueError('missing source receipt')
                if request is not None and not previous_request < request <= _MAX_SEQ:
                    raise ValueError('invalid guest request sequence')
                previous_seq, previous_request, previous_tick = sequence, request or 0, tick
                if role == 'source':
                    source[sequence] = coordinates
                else:
                    received.append((sequence, coordinates))
                if len(source) + len(received) > 100000:
                    raise ValueError('too many wire receipts')
        result['source_count'], result['receive_count'] = len(source), len(received)
        if not source or not received:
            raise ValueError('missing source or guest receipt')
        if any(source.get(seq) != pose for seq, pose in received):
            raise ValueError('guest receipt has no matching source pose')
        result['pass'] = True
    except (ValueError, OverflowError) as error:
        result['errors'].append(str(error))
    return result


def daemon(fd):
    # Secrets arrive through an inherited pipe, never argv, environment or logs.
    from fixture_udp import FixtureUDP
    with os.fdopen(fd, 'r', encoding='ascii') as channel:
        raw = channel.read(4097)
    if len(raw) > 4096:
        raise ValueError('oversized private configuration')
    config = json.loads(raw)
    adapter = FixtureUDP(fixture='test-only-fixture-1', source_lease=config['source'],
                         guest_lease=config['guest'], max_age_seconds=10)
    alive = [True]
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: alive.__setitem__(0, False))
    try:
        print('AUTHORITY_WIRE_READY port=' + str(adapter.address[1]), flush=True)
        while alive[0]:
            readable, _, _ = select.select([adapter.sock], [], [], .1)
            if readable:
                adapter.poll()
    finally:
        adapter.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config-fd', type=int, required=True)
    args = parser.parse_args()
    try:
        daemon(args.config_fd)
    except Exception:
        # Exception text could contain private configuration: do not log it.
        raise SystemExit('authority fixture UDP process failed') from None
