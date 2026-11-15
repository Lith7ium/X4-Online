"""Checks for an isolated natural-flight diagnostic, not session/gameplay proof.

An opt-in X4 runner is wired to emit these rows, but has not been tested in X4.
Source samples include the reference position and monotonic time used
for their finite difference, not merely the resulting rate. Times are seconds;
game time is sampled from X4, while each process supplies its own monotonic
clock. Source and guest clocks are never compared with each other. Labels and
samples are evidence supplied by the caller, not independently authenticated.
"""
import math


def _number(row, key):
    value = row[key]
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('nonfinite or nonnumeric ' + key)
    return value


def _seq(row):
    value = row['seq']
    if type(value) is not int or not 1 <= value <= 9007199254740991:
        raise ValueError('invalid sequence')
    return value


def _position(row):
    return tuple(_number(row, key) for key in ('x', 'y', 'z'))


def validate(*, epoch, index, frame, guest_actor, order, source, guest_writes, guest_readbacks):
    if not isinstance(epoch, str) or len(epoch) != 32 or any(c not in '0123456789abcdef' for c in epoch):
        raise ValueError('invalid epoch')
    if (type(index) is not int or index < 1 or not isinstance(frame, str) or not frame or
            not isinstance(guest_actor,str) or not guest_actor):
        raise ValueError('invalid identity/frame')
    if not isinstance(order, dict) or any(order.get(k) != v for k, v in
            (('epoch', epoch), ('index', index), ('frame', frame), ('pilot', 'present'), ('order', 'MoveWait'))):
        raise ValueError('missing bound pilot and order receipt')
    start_game = _number(order, 'game_time')
    order_real = _number(order, 'real_time')
    if start_game < 0 or order_real < 0: raise ValueError('invalid order time')
    if not isinstance(source, list) or len(source) < 3:
        raise ValueError('insufficient source samples')
    known = {}; source_positions_by_time = {}; last_seq = 0; last_real = order_real; last_game = start_game
    for row in source:
        if any(row.get(k) != v for k, v in (('epoch',epoch),('index',index),('frame',frame))):
            raise ValueError('source identity/frame changed')
        seq = _seq(row); real = _number(row,'real_time'); game = _number(row,'game_time')
        if seq <= last_seq or real <= last_real or game < last_game:
            raise ValueError('source sequence/time regressed')
        position = _position(row)
        rate = tuple(_number(row, key) for key in ('vx','vy','vz'))
        reference_time = _number(row,'reference_real_time')
        reference = tuple(_number(row,'reference_'+axis) for axis in 'xyz')
        dt = real-reference_time
        if reference_time < order_real or dt < .02 or dt > 1:
            raise ValueError('invalid finite-difference interval')
        if any(not math.isclose(rate[i],(position[i]-reference[i])/dt,rel_tol=1e-6,abs_tol=1e-6)
               for i in range(3)):
            raise ValueError('rate differs from source finite difference')
        if reference_time in source_positions_by_time and source_positions_by_time[reference_time] != reference:
            raise ValueError('reference contradicts prior recorded position')
        known[seq] = (position, rate)
        source_positions_by_time[real] = position
        last_seq,last_real,last_game = seq,real,game
    if last_game <= source[0]['game_time'] or last_real-source[0]['real_time'] < 1:
        raise ValueError('source time did not advance')
    initial = _position(source[0])
    if max(math.dist(initial, _position(row)) for row in source[1:]) < 10:
        raise ValueError('source did not move at least 10 m')
    if not isinstance(guest_writes,list) or not isinstance(guest_readbacks,list):
        raise ValueError('missing guest records')
    observed = {}; last_readback_seq = 0; last_readback_real = -1
    for row in guest_readbacks:
        seq = _seq(row)
        real = _number(row,'real_time')
        if seq <= last_readback_seq or real < 0 or real <= last_readback_real:
            raise ValueError('guest readback sequence/time invalid')
        if any(row.get(k) != v for k,v in (('epoch',epoch),('index',index),('frame',frame),('actor',guest_actor))):
            raise ValueError('guest readback identity/frame changed')
        observed[seq] = (real,_position(row));last_readback_seq,last_readback_real=seq,real
    matched = 0;last_seq = 0;last_real = -1;write_sequences=set()
    for row in guest_writes:
        seq = _seq(row); real = _number(row,'real_time')
        if seq <= last_seq or real < 0 or real <= last_real or seq not in known:
            raise ValueError('guest write sequence/time invalid')
        last_seq,last_real=seq,real;write_sequences.add(seq)
        if any(row.get(k) != v for k,v in (('epoch',epoch),('index',index),('frame',frame),('actor',guest_actor))):
            raise ValueError('guest identity/frame changed')
        source_position,source_rate=known[seq]
        if _position(row) != source_position or tuple(_number(row,k) for k in ('vx','vy','vz')) != source_rate:
            raise ValueError('guest write does not match source')
        target=tuple(_number(row,'target_'+axis) for axis in 'xyz')
        if any(abs(target[i]-(source_position[i]+source_rate[i]*.1))>1e-6 for i in range(3)):
            raise ValueError('invalid predicted position')
        if seq in observed:
            elapsed=observed[seq][0]-real
            if not 0 <= elapsed <= .75: raise ValueError('guest readback outside freshness window')
            if math.dist(target,observed[seq][1]) <= 5: matched+=1
    if any(seq not in write_sequences for seq in observed):
        raise ValueError('guest readback has no matching write')
    if matched < 3: raise ValueError('insufficient matching guest readbacks')
    return {'pass':True,'source_samples':len(source),'guest_writes':len(guest_writes),
            'matching_guest_readbacks':matched,'native_velocity_sampled':False,
            'npc_flight_proven_by_checker_alone':False,'collision_clearance_proven':False,
            'smoothness_proven':False,'shared_gameplay_proven':False}
