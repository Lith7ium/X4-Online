"""Read two explicitly granted fixture-player tracks in an existing session.

This bounded, private diagnostic owns the existing serialized TCP reader while
it is running. It does not launch X4, change a ship, authenticate a grant or
prove gameplay. The caller owns both client processes, the server, and all
cleanup, and must fence them after any uncertain operation. ``verify`` must
check those owned resources without pumping the host or using its TCP reader.
The bound test delivery remains owned until this diagnostic server shuts down;
this helper is not a reusable production-session lifecycle.
"""
import copy
import math
import select
import time

from authority.experimental_tcp_client_authority_motion import ExperimentalTCPClientAuthorityMotion, grant_value
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import motion_value
from authority.load_messages import MAX_INTEGER

MAX_PULLS_PER_PLAYER = 4096


def observe(*, host, world, grants, verify, deadline, operation_timeout=30, enabled=False,
            verify_transaction_boundary=None, progress=None):
    """Observe two rate-bearing 6D samples per handle; return no grant secrets.

    Grants map admitted connection handles to the caller's private assertions.
    An initial rate-less baseline is required. Unknown subsequent rates are
    skipped; zero is a valid measured rate. Velocity is a source-time derivative,
    not an engine-native velocity or proof of visible motion. The optional
    boundary guard runs immediately before and after each participant pull.
    An optional empty progress dict receives per-handle registry index, attempted
    pulls, returned samples, validated complete-rate samples and pulls lacking
    a confirmed post-boundary check, even on failure. When the optional boundary
    callback is absent, all pulls count as lacking that additional check.
    """
    if (enabled is not True or not callable(verify) or type(deadline) not in (int, float) or not math.isfinite(deadline) or
            type(operation_timeout) not in (int, float) or not math.isfinite(operation_timeout) or
            not 0 < operation_timeout <= 300 or
            (verify_transaction_boundary is not None and not callable(verify_transaction_boundary)) or
            (progress is not None and (type(progress) is not dict or progress)) or
            type(grants) is not dict or len(grants) != 2 or
            any(type(handle) is not int or not 1 <= handle <= MAX_INTEGER for handle in grants)):
        raise ValueError('invalid fixture observation context')
    original_grants = copy.deepcopy(grants)
    selected = {handle: grant_value(grant) for handle, grant in original_grants.items()}
    handles = tuple(sorted(selected))
    if (set(grant['index'] for grant in selected.values()) != {3, 4} or
            len({grant['incarnation'] for grant in selected.values()}) != 2 or
            len({grant['token'] for grant in selected.values()}) != 2):
        raise ValueError('fixture grants must identify distinct players')
    epoch = world.session.world_epoch
    if any(grant['session_epoch'] != epoch for grant in selected.values()):
        raise ValueError('fixture grant session differs')
    initial_players = world.session.players
    initial_ready = world.session.ready_players

    def check():
        if time.monotonic() >= deadline:
            raise TimeoutError('fixture player observation deadline')
        if (host._world is not world or world.session.world_epoch != epoch or
                world.session.state != 'running' or world.session.pending is not None or
                world.session.players != initial_players or world.session.ready_players != initial_ready or
                tuple(handle for handle, _ in initial_players) != handles or initial_ready != initial_players or
                grants != original_grants):
            raise RuntimeError('fixture participant context changed')
        if verify() is False:
            raise RuntimeError('fixture resource guard failed')
        if (time.monotonic() >= deadline or host._world is not world or
                world.session.world_epoch != epoch or world.session.state != 'running' or
                world.session.pending is not None or world.session.players != initial_players or
                world.session.ready_players != initial_ready or grants != original_grants):
            raise RuntimeError('fixture context changed during guard')

    check()
    delivery = ExperimentalTCPJobDelivery(host, enabled=True,
        timeout=min(operation_timeout, deadline - time.monotonic()))
    try:
        check()
        if delivery.bind_test_incarnations({handle: selected[handle]['incarnation'] for handle in handles}, enabled=True) is not True:
            raise RuntimeError('fixture participant bindings unconfirmed')
        check()
        owners = {}
        for handle in handles:
            grant = selected[handle]
            def grant_guard(candidate, expected=grant):
                check()
                return candidate == expected
            owners[handle] = ExperimentalTCPClientAuthorityMotion(delivery, enabled=True, grant=grant,
                guard=grant_guard, connection_handle=handle)
        evidence = {handle: [] for handle in handles}
        last = {handle: None for handle in handles}
        attempts = {handle: 0 for handle in handles}
        received = {handle: 0 for handle in handles}
        with_velocity = {handle: 0 for handle in handles}
        without_post_boundary = {handle: 0 for handle in handles}

        def record_progress(handle):
            if progress is not None:
                progress[handle] = {'registry_index': selected[handle]['index'], 'pulls_attempted': attempts[handle],
                                    'samples_received': received[handle], 'samples_with_complete_rates': with_velocity[handle],
                                    'pulls_without_post_boundary': without_post_boundary[handle]}

        for handle in handles:
            record_progress(handle)
        while any(len(evidence[handle]) < 2 for handle in handles):
            for handle in handles:
                if len(evidence[handle]) == 2:
                    continue
                check()
                if attempts[handle] >= MAX_PULLS_PER_PLAYER:
                    raise RuntimeError('fixture source sample limit exceeded')
                if verify_transaction_boundary is not None:
                    boundary_ok = verify_transaction_boundary()
                    check()
                    if boundary_ok is not True:
                        raise RuntimeError('fixture transaction boundary guard failed')
                attempts[handle] += 1
                without_post_boundary[handle] += 1
                record_progress(handle)
                sample = owners[handle].pull()
                if sample is not None:
                    received[handle] += 1
                    record_progress(handle)
                if verify_transaction_boundary is not None:
                    boundary_ok = verify_transaction_boundary()
                    check()
                    if boundary_ok is not True:
                        raise RuntimeError('fixture transaction boundary guard failed')
                    without_post_boundary[handle] -= 1
                    record_progress(handle)
                else:
                    check()
                if sample is not None:
                    sample = motion_value(sample)
                    grant = selected[handle]
                    prior = last[handle]
                    if (sample['version'] != 2 or sample['epoch'] != grant['epoch'] or
                            sample['generation'] != grant['generation'] or sample['index'] != grant['index'] or
                            sample['sector_macro'] != grant['sector_macro'] or
                            sample['sequence'] != (1 if prior is None else prior['sequence'] + 1) or
                            (prior is None and sample['velocity'] is not None) or
                            (prior is not None and sample['source_time'] <= prior['source_time'])):
                        raise ValueError('fixture player sample differs from granted track')
                    last[handle] = sample
                    if sample['velocity'] is not None:
                        with_velocity[handle] += 1
                    record_progress(handle)
                    if sample['velocity'] is not None:
                        evidence[handle].append({key: copy.deepcopy(sample[key]) for key in
                            ('sequence', 'source_time', 'x', 'y', 'z', 'orientation', 'velocity', 'angular_rate')})
                # Pump only after the pull releases the exclusive reader. Do not
                # ask the world to advance an unexpected lifecycle operation.
                check()
                host.tick(0, defer_world=True)
                check()
            if any(len(evidence[handle]) < 2 for handle in handles):
                check()
                select.select([], [], [], min(.05, max(0, deadline - time.monotonic())))
                check()
        return {'fixture_player_samples_observed': True,
                'players': [{'connection_handle': handle, 'registry_index': selected[handle]['index'],
                             'sector_macro': selected[handle]['sector_macro'], 'samples': evidence[handle]}
                            for handle in handles],
                'server_x4_motion_applied': False, 'native_velocity_proven': False,
                'cross_process_identity_proven': False, 'multiplayer_gameplay_proven': False}
    except BaseException:
        delivery._failed = True
        host._failed = True
        raise
