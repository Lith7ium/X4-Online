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


class SourceProbeDiagnostics:
    """Non-secret progress and guard costs; never performs a guard itself."""

    def __init__(self):
        self.started_at = time.monotonic()
        self.phase_started_at = self.started_at
        self.phase = 'initializing'
        self.phase_seconds = {}
        self.full_guard_calls = 0
        self.full_guard_seconds = 0.0
        self.saved_checkpoint_guard_calls = 0
        self.saved_checkpoint_guard_seconds = 0.0
        self.pump_process_guard_calls = 0
        self.pump_client_guard_calls = 0
        self.samples_received = 0
        self.pull_attempts = 0
        self.empty_pulls = 0
        self.last_pull_seconds = None
        self.prevalidated_samples = 0
        self.confirmed_client_receipts = 0

    def enter(self, phase):
        now = time.monotonic()
        self.phase_seconds[self.phase] = self.phase_seconds.get(self.phase, 0.0) + now - self.phase_started_at
        self.phase = phase
        self.phase_started_at = now

    def snapshot(self):
        now = time.monotonic()
        phase_seconds = dict(self.phase_seconds)
        phase_seconds[self.phase] = phase_seconds.get(self.phase, 0.0) + now - self.phase_started_at
        return {'phase': self.phase, 'elapsed_seconds': now - self.started_at,
                'phase_seconds': phase_seconds, 'full_guard_calls': self.full_guard_calls,
                'full_guard_seconds': self.full_guard_seconds,
                'saved_checkpoint_guard_calls': self.saved_checkpoint_guard_calls,
                'saved_checkpoint_guard_seconds': self.saved_checkpoint_guard_seconds,
                'pump_process_guard_calls': self.pump_process_guard_calls,
                'pump_client_guard_calls': self.pump_client_guard_calls,
                'samples_received': self.samples_received,
                'pull_attempts': self.pull_attempts, 'empty_pulls': self.empty_pulls,
                'last_pull_seconds': self.last_pull_seconds,
                'prevalidated_samples': self.prevalidated_samples,
                'confirmed_client_receipts': self.confirmed_client_receipts}


def run(*, sock, settings, index, baseline, guard, pump, active, host, world,
        identity, verify, verify_process, timeout=90, candidate_indices=None,
        client_motion=False, verify_stopped=None, diagnostics=None,
        diagnostic_timeouts=None):
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
            or (diagnostics is not None and not isinstance(diagnostics, SourceProbeDiagnostics))
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
    source_timeout = timeout
    delivery_timeout = 15
    if diagnostic_timeouts is not None:
        if (not client_motion or type(diagnostic_timeouts) is not dict or
                set(diagnostic_timeouts) != {'total', 'source_bind_stage', 'source_operation', 'tcp_send', 'client_bind'}):
            raise ValueError('invalid extended diagnostic timeouts')
        total = diagnostic_timeouts['total']
        source_bind = diagnostic_timeouts['source_bind_stage']
        source_timeout = diagnostic_timeouts['source_operation']
        delivery_timeout = diagnostic_timeouts['tcp_send']
        client_bind = diagnostic_timeouts['client_bind']
        values = (total, source_bind, source_timeout, delivery_timeout, client_bind)
        if (any(type(value) not in (int, float) or not math.isfinite(value) for value in values) or
                not 0 < client_bind <= 30 or not 0 < source_bind <= 120 or
                not client_bind < delivery_timeout < source_timeout <= 300 or
                not source_timeout < total <= 86400):
            raise ValueError('invalid extended diagnostic timeout ordering')
        timeout = total

        # An admitted peer with its admission response drained has no TCP idle
        # deadline. Do not invent credit if that condition changes mid-probe.
        participant = active.participant
        client_motion_config = participant.motion_worker_config
        if (type(client_motion_config) is not dict or
                type(client_motion_config.get('timeout')) not in (int, float) or
                client_motion_config['timeout'] != client_bind or
                participant._motion_worker_timeout_snapshot != client_bind):
            raise RuntimeError('client motion timeout differs from worker configuration')
        control = host._control
        peer_socket = participant.server_tcp
        peer = control._peers.get(peer_socket)
        if (peer is None or peer.get('stage') != 'admitted' or peer.get('deadline') is not None):
            raise RuntimeError('diagnostic TCP idle fence unavailable')
    else:
        control = peer_socket = peer = participant = client_motion_config = None
    deadline = min(guard.deadline, time.monotonic() + timeout)

    def check_deadline():
        if time.monotonic() >= deadline:
            raise TimeoutError('source diagnostic deadline')
        if control is not None and (host._control is not control or
                active.participant is not participant or
                participant.server_tcp is not peer_socket or
                participant.motion_worker_config is not client_motion_config or
                type(client_motion_config.get('timeout')) not in (int, float) or
                client_motion_config['timeout'] != client_bind or
                participant._motion_worker_timeout_snapshot != client_bind or
                control._peers.get(peer_socket) is not peer or peer.get('stage') != 'admitted' or
                peer.get('deadline') is not None):
            raise RuntimeError('diagnostic TCP idle fence changed')

    def checked_operation(operation, *args, **kwargs):
        check_deadline()
        result = operation(*args, **kwargs)
        check_deadline()
        return result

    def active_guard():
        check_deadline()
        if diagnostics is None:
            verify()
        else:
            diagnostics.full_guard_calls += 1
            started_at = time.monotonic()
            try:
                verify()
            finally:
                diagnostics.full_guard_seconds += time.monotonic() - started_at
        check_deadline()
        return True

    def pump_guard():
        # The enclosing source IPC rechecks its full context before and after
        # each saved-guard call. While the helper hashes, only process/log and
        # client liveness need pumping; re-hashing source on each IPC byte or
        # wait poll would repeat the same check without adding a boundary.
        check_deadline()
        if diagnostics is not None:
            diagnostics.pump_process_guard_calls += 1
        verify_process()
        if diagnostics is not None:
            diagnostics.pump_client_guard_calls += 1
        if active.participant.check_active(server_checked=True) is not True:
            raise RuntimeError('retained client unavailable')
        if diagnostics is not None:
            diagnostics.pump_process_guard_calls += 1
        verify_process()
        check_deadline()
        return True
    if diagnostics is not None:
        diagnostics.enter('initial_verification')
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
        if diagnostics is None:
            return guard.check() is True
        diagnostics.saved_checkpoint_guard_calls += 1
        started_at = time.monotonic()
        try:
            return guard.check() is True
        finally:
            diagnostics.saved_checkpoint_guard_seconds += time.monotonic() - started_at

    staged_samples = []

    def capture_sample(value):
        staged_samples.append(copy.deepcopy(value))
        if diagnostics is not None:
            # Parsed source sample staged locally; not a delivered receipt.
            diagnostics.prevalidated_samples += 1
        return True
    delivery = ExperimentalTCPJobDelivery(host, enabled=True, timeout=delivery_timeout)
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

    if diagnostics is not None:
        diagnostics.enter('bind_source')
    binding_options = {} if diagnostic_timeouts is None else {'bind_timeout': source_bind}
    source = checked_operation(bind_running_source_motion,
        sock, motion, process=process, lease=settings['lease'], attempt=settings['attempt'],
        epoch=settings['epoch'], generation=settings['generation'], world=world,
        client_guard=active_guard, timeout=source_timeout, saved_baseline=settings['baseline'],
        saved_guard=saved_baseline_guard, select_recipients=select_recipients,
        validate_sample=capture_sample, candidate_indices=candidate_indices, **binding_options,
    )
    if candidate_indices is not None:
        if diagnostics is not None:
            diagnostics.enter('select_candidate')
        index = checked_operation(source.request_candidate)
    if diagnostics is not None:
        diagnostics.enter('register_source')
    checked_operation(source.register_saved, index)
    if diagnostics is not None:
        diagnostics.enter('collect_samples')
    samples = []
    for _ in range(20):
        previous_count = len(staged_samples)
        if diagnostics is not None:
            diagnostics.pull_attempts += 1
            pull_started_at = time.monotonic()
        try:
            received = checked_operation(source.pull)
        finally:
            if diagnostics is not None:
                diagnostics.last_pull_seconds = time.monotonic() - pull_started_at
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
                if diagnostics is not None:
                    diagnostics.confirmed_client_receipts += 1
            samples.append(staged_samples[-1])
            if diagnostics is not None:
                diagnostics.samples_received = len(samples)
            if len(samples) == 2:
                break
        elif received is not None:
            raise RuntimeError('uncaptured motion receipt')
        elif diagnostics is not None:
            diagnostics.empty_pulls += 1
        time.sleep(.1)
    if len(samples) != 2:
        raise RuntimeError('two server source samples unavailable')
    if diagnostics is not None:
        diagnostics.enter('stop_source')
    if checked_operation(source.stop_remote) is not True:
        raise RuntimeError('source stop unconfirmed')
    active_guard()
    if diagnostics is not None:
        diagnostics.enter('stop_checkpoint_guard')
    if checked_operation(guard.stop) is not True:
        raise RuntimeError('checkpoint guard stop unconfirmed')
    active_guard()
    if client_motion:
        if diagnostics is not None:
            diagnostics.enter('stop_client')
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
    if diagnostics is not None:
        diagnostics.enter('close_source')
    checked_operation(source.close)
    public_fields = ('sequence', 'sector_macro', 'source_time', 'x', 'y', 'z', 'velocity')
    public_samples = [{key: sample[key] for key in public_fields} for sample in samples]
    if diagnostics is not None:
        diagnostics.enter('complete')
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
