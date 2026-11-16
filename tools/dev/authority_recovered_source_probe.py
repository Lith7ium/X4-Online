"""One explicitly selected saved-registry source in a private running join.

The optional one-client mode requires correlated motion receipts and an
explicitly stopped client worker. It does not prove visible motion or historic
identity. Caller owns both X4 processes, all sockets, the checkpoint writer
fence, log watching, and global failure cleanup.
"""
import copy
import math
import os
import time
from pathlib import Path

from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion, motion_digest
from authority_motion_ipc_supervisor import bind_running_source_motion
from authority_tcp_job_client_live import socket_owner
from authority_tcp_native_worker import check_process


def run(*, sock, settings, index, baseline, guard, pump, active, host, world,
        identity, verify, verify_process, timeout=90, candidate_indices=None,
        client_motion=False, verify_stopped=None):
    def valid_index(value):
        return type(value) is int and 1 <= value <= settings['baseline']

    if candidate_indices is None:
        invalid_selection = not valid_index(index)
    else:
        invalid_selection = (
            index is not None
            or type(candidate_indices) is not tuple
            or not 1 <= len(candidate_indices) <= 32
            or any(not valid_index(candidate) for candidate in candidate_indices)
            or len(set(candidate_indices)) != len(candidate_indices)
        )
    if (invalid_selection
            or type(identity) is not tuple or len(identity) != 2
            or any(type(value) is not int or value < 1 for value in identity)
            or not callable(verify) or not callable(verify_process)
            or type(client_motion) is not bool
            or (client_motion and not callable(verify_stopped))
            or type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 0 < timeout <= 90
            or guard.status[:3] != ('ready', settings['epoch'], settings['baseline'])):
        raise ValueError('diagnostic source context invalid')
    pinned_baseline = world._baseline
    if (type(pinned_baseline) is not tuple or len(pinned_baseline) != 2
            or pinned_baseline[1] != baseline
            or world.session.state != 'running' or world.session.pending is not None or
            world.session.baseline_id is not None):
        raise RuntimeError('running source does not retain the admitted checkpoint')
    deadline = min(guard.deadline, time.monotonic() + timeout)

    def check_deadline():
        if time.monotonic() >= deadline:
            raise TimeoutError('source diagnostic deadline')

    def active_guard():
        check_deadline()
        verify()
        check_deadline()
        return True

    def pump_guard():
        # The enclosing source IPC rechecks its full context before and after
        # each saved-guard call. While the helper hashes, only process/log and
        # client liveness need pumping; re-hashing source on each IPC byte or
        # wait poll would repeat the same check without adding a boundary.
        check_deadline()
        verify_process()
        if active.participant.check_active(server_checked=True) is not True:
            raise RuntimeError('retained client unavailable')
        verify_process()
        check_deadline()
        return True
    pump.activate(host=host, guard=pump_guard)
    active_guard()
    executable_stat = os.stat(Path('/proc') / str(identity[0]) / 'exe')
    process = {'pid': identity[0], 'start_ticks': identity[1],
               'exe_dev': executable_stat.st_dev, 'exe_ino': executable_stat.st_ino}

    def saved_baseline_guard(epoch, count):
        if ((epoch, count) != (settings['epoch'], settings['baseline'])
                or guard.status[:3] != ('ready', epoch, count)):
            return False
        if (world._baseline != pinned_baseline or world.session.state != 'running'
                or world.session.pending is not None or world.session.baseline_id is not None):
            return False
        return guard.check() is True

    staged_samples = []

    def capture_sample(value):
        staged_samples.append(copy.deepcopy(value))
        return True
    delivery = ExperimentalTCPJobDelivery(host, enabled=True, timeout=15)
    motion = ExperimentalTCPMotion(delivery, enabled=True)
    selected_recipient = None
    if client_motion:
        members = delivery.membership()
        if len(members) != 1 or len(world.session.ready_players) != 1:
            raise RuntimeError('exactly one admitted motion recipient required')
        handle = world.session.ready_players[0][0]
        if members[0]['id'] != 'peer_' + str(handle):
            raise RuntimeError('motion recipient differs from admitted client')
        selected_recipient = copy.deepcopy(members[0])

    def select_recipients(_sample, members):
        if not client_motion:
            return []
        if tuple(members) != (selected_recipient,):
            raise RuntimeError('diagnostic motion recipient changed')
        return [copy.deepcopy(selected_recipient)]

    source = bind_running_source_motion(
        sock, motion, process=process, lease=settings['lease'], attempt=settings['attempt'],
        epoch=settings['epoch'], generation=settings['generation'], world=world,
        client_guard=active_guard, timeout=timeout, saved_baseline=settings['baseline'],
        saved_guard=saved_baseline_guard, select_recipients=select_recipients,
        validate_sample=capture_sample, candidate_indices=candidate_indices,
    )
    if candidate_indices is not None:
        index = source.request_candidate()
    source.register_saved(index)
    samples = []
    for _ in range(20):
        previous_count = len(staged_samples)
        received = source.pull()
        if len(staged_samples) > previous_count:
            if len(staged_samples) != previous_count + 1:
                raise RuntimeError('ambiguous source sample')
            if client_motion:
                if (received is None or received != staged_samples[-1]
                        or motion_digest(received) != motion_digest(staged_samples[-1])):
                    raise RuntimeError('motion receipt differs from source sample')
                track_key = (settings['epoch'], settings['generation'], index)
                track = motion._tracks.get(track_key)
                recipient_key = (selected_recipient['id'], selected_recipient['incarnation'])
                expected_receipt = (received['sequence'], motion_digest(received))
                if track is None or track['peer_samples'].get(recipient_key) != expected_receipt:
                    raise RuntimeError('motion receipt digest not recorded for client')
            samples.append(staged_samples[-1])
            if len(samples) == 2:
                break
        elif received is not None:
            raise RuntimeError('uncaptured motion receipt')
        time.sleep(.1)
    if len(samples) != 2:
        raise RuntimeError('two server source samples unavailable')
    if source.stop_remote() is not True:
        raise RuntimeError('source stop unconfirmed')
    active_guard()
    if guard.stop() is not True:
        raise RuntimeError('checkpoint guard stop unconfirmed')
    active_guard()
    if client_motion:
        local_address, peer_address = sock.getsockname(), sock.getpeername()
        socket_fd = sock.fileno()
        socket_stat = os.fstat(socket_fd)
        socket_identity = (socket_stat.st_dev, socket_stat.st_ino)
        ready_players = tuple(world.session.ready_players)

        def stopped_source():
            # Called while the worker IPC is exclusively being read: do not
            # enter participant.check_active, the helper pump, or TCP poll.
            check_deadline()
            check_process(process)
            verify_stopped()
            current_stat = os.fstat(socket_fd)
            if (source.state != 'remote_stopped' or sock.fileno() != socket_fd
                    or (current_stat.st_dev, current_stat.st_ino) != socket_identity
                    or sock.getsockname() != local_address or sock.getpeername() != peer_address
                    or socket_owner(peer_address, local_address, process) is not True
                    or world.session.state != 'running' or world.session.pending is not None
                    or tuple(world.session.ready_players) != ready_players
                    or tuple(world.session.players) != ready_players):
                return False
            check_process(process)
            check_deadline()
            return True

        if active.participant.stop_motion_worker(source_stopped=stopped_source) is not True:
            raise RuntimeError('client motion worker stop unconfirmed')
        if stopped_source() is not True:
            raise RuntimeError('source fence changed after client stop')
    source.close()
    public_fields = ('sequence', 'sector_macro', 'source_time', 'x', 'y', 'z', 'velocity')
    public_samples = [{key: sample[key] for key in public_fields} for sample in samples]
    return {
        'index': index,
        'candidate_selected': candidate_indices is not None,
        'candidate_is_reservation': False,
        'samples': public_samples,
        'source_stopped_before_disconnect': True,
        'server_only': not client_motion,
        'client_motion_receipts_confirmed': client_motion,
        'client_worker_stop_confirmed': client_motion,
        'client_receipt_sample_sha256': [motion_digest(sample) for sample in samples] if client_motion else [],
        'second_sample_velocity_present': public_samples[1]['velocity'] is not None,
        'client_motion_proven': False,
        'client_motion_visible_proven': False,
        'smooth_motion_proven': False,
        'cross_process_identity_proven': False,
    }
