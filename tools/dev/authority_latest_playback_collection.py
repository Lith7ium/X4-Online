"""Bounded, single-owner collection for one latest-position playback fixture.

Queue acceptance and participant receipts remain separate. The caller owns
source STOP, native playback evidence, pause, departure and process cleanup.
An exception fences the source and its host; no operation is retried here.
"""
from contextlib import nullcontext
import copy
import math
import threading
import time

from authority.experimental_tcp_motion import check_motion_progress, motion_digest, motion_value


def collect_latest_playback(*, source, motion, host, recipient, deadline, check,
                            scope=None, sample_count=26, interval=.2, progress=None,
                            sample_version=1):
    """Collect one registered track, drain its final ACK, then fence new motion.

    ``check`` must return True and must not pump a socket owner. ``scope`` is
    an optional per-operation identity-context factory. Callbacks are bounded
    caller responsibilities. ``progress`` receives detached, bounded counters
    and sample lists, including on failure. Operation and receipt times are
    host monotonic observations; no source/client clock origins are compared.
    ``sample_version`` explicitly pins legacy game-clock samples (1, default)
    or capture-clock samples (3). Version 3 timing rows additionally retain
    source game time and source capture time in their original clock domains.
    """
    if (not callable(check) or (scope is not None and not callable(scope)) or
            type(sample_count) is not int or not 2 <= sample_count <= 26 or
            type(sample_version) is not int or sample_version not in (1, 3) or
            type(interval) not in (int, float) or not math.isfinite(interval) or not 0 < interval <= 1 or
            type(deadline) not in (int, float) or not math.isfinite(deadline) or
            (progress is not None and type(progress) is not dict) or
            type(recipient) is not dict or set(recipient) != {'id', 'incarnation'}):
        raise ValueError('invalid bounded latest playback collection')
    owner = threading.get_ident()
    delivery = motion._delivery
    control = host._control
    world = host._world
    session = world.session
    latest = control._latest_motion
    recipient = copy.deepcopy(recipient)
    peer_key = (recipient['id'], recipient['incarnation'])
    indices = source._indices
    if (source._motion is not motion or delivery._host is not host or not source._latest or
            source._owner != owner or source.state != 'ready' or len(indices) != 1 or
            control._latest_source is not source or latest is None):
        raise ValueError('one ready owned latest source track required')
    index = next(iter(indices))
    track_key = (source._epoch, source._generation, index)
    track = motion._tracks[track_key]
    members = tuple(copy.deepcopy(delivery.membership()))
    if members != (recipient,):
        raise ValueError('one fixed admitted recipient required')
    handles, peers = delivery._peers()
    if len(handles) != 1:
        raise ValueError('one admitted socket required')
    handle = handles[0]
    connection, peer = peers[handle]
    players = tuple(session.players)
    ready_players = tuple(session.ready_players)
    queued, acknowledged, known = [], [], {}
    stats = {'operations': {}, 'sample_times': [], 'ack_times': [],
             'first_frame_started_at': None, 'barrier_established': False, 'empty_pulls': 0}
    last_clock = -math.inf
    first_protected = False
    last_ack = None
    next_pull_at = 0
    pending_started_at = None

    def now():
        nonlocal last_clock
        value = time.monotonic()
        if not math.isfinite(value) or value < last_clock:
            raise RuntimeError('host monotonic clock regressed')
        last_clock = value
        return value

    started_at = now()
    stats['started_at'] = started_at

    def publish(state):
        if progress is not None:
            progress.clear()
            progress.update(copy.deepcopy({'state': state, 'stats': stats,
                'queued_sequences': [row['sequence'] for row in queued],
                'acknowledged_sequences': [row['sequence'] for row in acknowledged],
                'queued_samples': queued, 'acknowledged_samples': acknowledged}))

    def context():
        if (threading.get_ident() != owner or now() >= deadline or
                source._owner != owner or source.state not in ('ready', 'pulling') or
                source._motion is not motion or not source._latest or
                host._control is not control or host._world is not world or world.session is not session or
                delivery._host is not host or motion._delivery is not delivery or
                control._latest_source is not source or control._latest_motion is not latest or
                motion._tracks.get(track_key) is not track or source._indices != {index} or
                source._epoch != track_key[0] or source._generation != track_key[1] or
                source._motion._failed or delivery._failed or host._failed or control._failed or
                host._busy or delivery._active or control._reader_lease is not None or
                session.state != 'running' or session.pending is not None or
                tuple(session.players) != players or tuple(session.ready_players) != ready_players or
                latest.world_blocked or (latest.blocked and not stats['barrier_established']) or
                tuple(delivery.membership()) != members or
                control._peers.get(connection) is not peer or peer['stage'] != 'admitted' or
                delivery._incarnations.get(handle) != recipient['incarnation']):
            raise RuntimeError('latest playback deadline or context changed')

    def record_operation(name, seconds):
        row = stats['operations'].setdefault(name, {'calls': 0, 'seconds': 0, 'max_seconds': 0})
        row['calls'] += 1
        row['seconds'] += seconds
        row['max_seconds'] = max(row['max_seconds'], seconds)

    def guarded_check():
        context()
        before = now()
        try:
            if check() is not True:
                raise RuntimeError('latest playback external guard failed')
        finally:
            record_operation('check', now() - before)
        context()

    def observe_ack():
        nonlocal last_ack, first_protected
        receipt = track['peer_samples'].get(peer_key)
        if receipt == last_ack:
            return  # Re-reading an unchanged receipt is not a new ACK.
        if (type(receipt) is not tuple or len(receipt) != 2 or
                type(receipt[0]) is not int or receipt[0] not in known or
                receipt[1] != known[receipt[0]][1] or
                (last_ack is None and receipt[0] != 1) or
                (last_ack is not None and receipt[0] <= last_ack[0])):
            raise RuntimeError('unknown, regressed or mismatched latest playback ACK')
        sample = known[receipt[0]][0]
        acknowledged.append(copy.deepcopy(sample))
        last_ack = receipt
        first_protected = True
        stats['ack_times'].append({'sequence': receipt[0], 'observed_at': now()})
        publish('collecting')

    def observe_poll(result):
        nonlocal pending_started_at
        done, sample = result
        if not done:
            return
        if sample is not None:
            value = motion_value(sample)
            sequence = len(queued) + 1
            if (value['version'] != sample_version or value['sequence'] != sequence or
                    (value['epoch'], value['generation'], value['index']) != track_key or
                    (queued and value['sector_macro'] != queued[0]['sector_macro'])):
                raise RuntimeError('latest playback source identity or sequence changed')
            try:
                check_motion_progress(value, queued[-1] if queued else None)
            except ValueError as error:
                raise RuntimeError('latest playback source clocks or version changed') from error
            queued.append(value)
            known[sequence] = (value, motion_digest(value))
            sample_timing = {'sequence': sequence, 'queued_at': now(),
                'pull_elapsed_seconds': now() - pending_started_at}
            if sample_version == 3:
                sample_timing['source_time'] = value['source_time']
                sample_timing['capture_time'] = value['capture_time']
            stats['sample_times'].append(sample_timing)
        else:
            stats['empty_pulls'] += 1
        pending_started_at = None
        # Retain a completed queue acceptance before any later guard failure.
        publish('collecting')

    def invoke(name, operation):
        with scope() if scope is not None else nullcontext():
            guarded_check()
            before = now()
            try:
                value = operation()
                if name == 'pump':
                    observe_ack()  # Immediately after this collector's only TCP poll.
                elif name == 'poll':
                    observe_poll(value)
            finally:
                record_operation(name, now() - before)
            guarded_check()
        context()
        return value

    try:
        guarded_check()
        if track['sequence'] != 0 or track['peer_samples'] or not control._motion_idle():
            raise RuntimeError('fresh playback enrollment required')
        publish('collecting')
        while True:
            invoke('pump', lambda: host.tick(0, defer_world=True))
            if queued and not first_protected:
                active = peer.get('motion_active')
                if (active is not None and active['key'] == track_key and active['sent'] > 0 and
                        active['expected']['request_id'] == 1 and
                        active['expected']['sample_sha256'] == known[1][1]):
                    first_protected = True
                    stats['first_frame_started_at'] = now()
                    publish('collecting')
            if source.state == 'pulling':
                invoke('poll', source.poll_latest)
            if len(queued) == sample_count:
                if (source.state == 'ready' and last_ack == (sample_count, known[sample_count][1]) and
                        control._motion_idle()):
                    def establish_barrier():
                        if control.motion_barrier() is not True:
                            raise RuntimeError('final latest playback barrier did not drain')
                        stats['barrier_established'] = True
                    invoke('barrier', establish_barrier)
                    stats['finished_at'] = now()
                    stats['elapsed_seconds'] = stats['finished_at'] - started_at
                    publish('complete')
                    return copy.deepcopy({'queued_samples': queued,
                        'acknowledged_samples': acknowledged, 'stats': stats})
            elif source.state == 'ready' and (not queued or first_protected) and now() >= next_pull_at:
                before = now()
                if invoke('begin', source.begin_latest):
                    pending_started_at = before
                    next_pull_at = before + interval
            time.sleep(min(.002, max(0, deadline - now())))
    except BaseException:
        publish('failed')
        source._fail()
        raise
