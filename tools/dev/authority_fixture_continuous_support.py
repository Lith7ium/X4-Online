"""Validate bounded local source/guest write evidence; no game calls."""
import math
import re


def _rows(lines, kind):
    prefix = 'AUTHORITY_CONTINUOUS_' + kind + ' '
    for line in lines:
        if prefix in line:
            fields = line.split(prefix, 1)[1].strip().split()
            row = {}
            for field in fields:
                key, value = field.split('=', 1)
                if key in row:
                    raise ValueError('duplicate field')
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError('nonfinite field')
                row[key] = number
            yield row


def validate(source_lines, guest_lines):
    result = {'pass': False, 'errors': []}
    try:
        source_lines, guest_lines = list(source_lines), list(guest_lines)
        enroll = re.compile(r'AUTHORITY_APPLY_ENROLL ship=([0-9a-f]{64}) sector=([0-9a-f]{64})')
        def enrollment(lines):
            rows = [enroll.search(line) for line in lines if 'AUTHORITY_APPLY_ENROLL' in line]
            if len(rows) != 1 or rows[0] is None:
                raise ValueError('missing fixture enrollment')
            return rows[0].groups()
        if enrollment(source_lines) != enrollment(guest_lines):
            raise ValueError('source and guest fixture identities differ')
        source_pattern = re.compile(r'AUTHORITY_WIRE_SOURCE tick=\d+ seq=(\d+) x=(\S+) y=(\S+) z=(\S+)')
        guest_pattern = re.compile(r'AUTHORITY_WIRE_RECEIVE tick=\d+ request=\d+ seq=(\d+) x=(\S+) y=(\S+) z=(\S+)')
        def poses(lines, pattern):
            values = {}
            for line in lines:
                match = pattern.search(line)
                if match:
                    seq = int(match.group(1))
                    if seq in values:
                        raise ValueError('duplicate pose sequence')
                    values[seq] = tuple(float(v) for v in match.groups()[1:])
            return values
        sent, received = poses(source_lines, source_pattern), poses(guest_lines, guest_pattern)
        source = list(_rows(source_lines, 'SOURCE'))
        writes = list(_rows(guest_lines, 'WRITE'))
        observations = list(_rows(guest_lines, 'OBSERVE'))
        # Preserve the actual log order: a readback must follow its write, and
        # another write cannot hide a missing intermediate readback.
        pending = None
        for line in guest_lines:
            if 'AUTHORITY_CONTINUOUS_WRITE ' in line:
                events = list(_rows([line], 'WRITE'))
                if len(events) != 1 or pending is not None:
                    raise ValueError('write before prior readback')
                pending = events[0]['seq']
            elif 'AUTHORITY_CONTINUOUS_OBSERVE ' in line:
                events = list(_rows([line], 'OBSERVE'))
                if len(events) != 1 or pending != events[0]['seq']:
                    raise ValueError('readback without preceding write')
                pending = None
        rates = {r['seq']: (r['vx'], r['vy'], r['vz']) for r in source}
        if len(rates) != len(source):
            raise ValueError('duplicate source rate')
        by_seq = {r['seq']: r for r in observations}
        if len(by_seq) != len(observations) or len(writes) < 10:
            raise ValueError('insufficient writes or duplicate observations')
        errors, before, after, assessed = [], [], [], []
        unobserved_final = 0
        previous = 0
        for index, row in enumerate(writes):
            seq = row['seq']
            if seq <= previous or seq not in rates:
                raise ValueError('missing or unordered source')
            previous = seq
            velocity = tuple(row[k] for k in ('vx','vy','vz'))
            if velocity != rates[seq] or not 0 <= math.dist(velocity, (0,0,0)) <= 5000:
                raise ValueError('source rate mismatch')
            position = tuple(row[k] for k in ('x','y','z'))
            if sent.get(seq) != position or received.get(seq) != position:
                raise ValueError('write pose does not match sent and received sample')
            target = tuple(row['target_'+k] for k in ('x','y','z'))
            if any(abs(target[i]-(position[i]+velocity[i]*.1)) > 1e-6 for i in range(3)):
                raise ValueError('prediction mismatch')
            if seq not in by_seq:
                if index != len(writes)-1:
                    raise ValueError('missing intermediate readback')
                unobserved_final = 1
                continue
            obs = by_seq[seq]
            after.append(tuple(obs[k] for k in ('x','y','z')))
            before.append(tuple(row['before_'+k] for k in ('x','y','z')))
            errors.append(math.dist(after[-1], target))
            assessed.append(row)
        if len(after) < 10:
            raise ValueError('insufficient observed writes')
        movement = max(math.dist(after[0], p) for p in after[1:])
        improvements = sum(error <= 5 and math.dist(prior, tuple(row['target_'+k] for k in ('x','y','z'))) >= error + 3
                           for error, prior, row in zip(errors, before, assessed))
        result.update(writes=len(writes), readbacks=len(after), observed_motion_m=movement,
                      unobserved_final_write=unobserved_final,
                      improving_readbacks=improvements, max_target_error_m=max(errors),
                      mean_target_error_m=sum(errors)/len(errors))
        if movement < 10:
            raise ValueError('guest readbacks show less than 10 m movement')
        if improvements < 5:
            raise ValueError('fewer than five readbacks approach their targets')
        # A final write can precede the tick limit with no later sample; it is
        # reported separately and is never counted as an observed write.
        result['pass'] = True
    except (KeyError, ValueError, OverflowError, ZeroDivisionError) as error:
        result['errors'].append(str(error))
    return result
