"""One explicitly selected saved-registry source in a private running join.

The optional one-client mode requires correlated motion receipts and an
explicitly stopped client worker. It does not prove visible motion or historic
identity. Caller owns both X4 processes, all sockets, the checkpoint writer
fence, log watching, and global failure cleanup.
"""
import copy
from contextlib import nullcontext
import math
import os
import re
import sys
import time
from pathlib import Path

from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion, motion_digest
from authority_motion_ipc_supervisor import bind_running_source_motion
from authority_tcp_job_client_live import socket_owner
from authority_tcp_native_worker import check_process


class SourceProbeDiagnostics:
    """Non-secret progress and guard costs; never performs a guard itself."""

    _TRACE_FILES = frozenset({
        'authority_recovered_source_probe.py', 'experimental_source_motion_ipc.py',
        'experimental_tcp_motion.py', 'experimental_tcp_job_delivery.py',
        'experimental_tcp_control.py', 'experimental_tcp_latest_motion.py',
    })
    _MAX_CALL_SITES = 128

    def __init__(self, *, include_guard_callsites=False):
        if type(include_guard_callsites) is not bool:
            raise ValueError('guard callsite option must be boolean')
        self.include_guard_callsites = include_guard_callsites
        self.guard_call_sites = {}
        self.guard_call_sites_dropped = 0
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

    def guard_call_site(self):
        """Capture only code locations, never frame locals or callback values."""
        if not self.include_guard_callsites:
            return None
        try:
            frame = sys._getframe(1)
            locations = []
            while frame is not None and len(locations) < 8:
                filename = os.path.basename(frame.f_code.co_filename)
                if filename in self._TRACE_FILES:
                    locations.append((filename, frame.f_code.co_name, frame.f_lineno))
                frame = frame.f_back
            return self.phase, tuple(locations)
        except Exception:
            return None

    def record_guard_call(self, kind, site, seconds):
        # Timing is supplemental and must not replace a guard exception.
        if site is None:
            return
        try:
            key = (kind, *site)
            if key not in self.guard_call_sites:
                if len(self.guard_call_sites) >= self._MAX_CALL_SITES:
                    self.guard_call_sites_dropped += 1
                    return
                self.guard_call_sites[key] = {'calls': 0, 'seconds': 0.0}
            row = self.guard_call_sites[key]
            row['calls'] += 1
            row['seconds'] += seconds
        except Exception:
            pass

    def enter(self, phase):
        now = time.monotonic()
        self.phase_seconds[self.phase] = self.phase_seconds.get(self.phase, 0.0) + now - self.phase_started_at
        self.phase = phase
        self.phase_started_at = now

    def snapshot(self):
        now = time.monotonic()
        phase_seconds = dict(self.phase_seconds)
        phase_seconds[self.phase] = phase_seconds.get(self.phase, 0.0) + now - self.phase_started_at
        result = {'phase': self.phase, 'elapsed_seconds': now - self.started_at,
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
        if self.include_guard_callsites:
            result['guard_call_sites'] = [
                {'guard': kind, 'phase': phase,
                 'stack': [{'file': filename, 'function': function, 'line': line}
                           for filename, function, line in locations],
                 **dict(timing)}
                for (kind, phase, locations), timing in sorted(self.guard_call_sites.items())
            ]
            result['guard_call_sites_dropped'] = self.guard_call_sites_dropped
        return result


def perform_saved_apply(source, sample, received_at, *, active_guard, checked_operation,
                        record_apply_intent, diagnostics=None):
    """Exactly one read-only preflight and, only if ready, one possible write."""
    if diagnostics is not None:
        diagnostics.enter('saved_apply_preflight')
    active_guard()
    status = checked_operation(source.preflight, sample)
    if status not in ('near', 'ready'):
        raise RuntimeError('saved apply preflight unconfirmed')
    result = {'preflight': status, 'apply_requested': False, 'full_sample_age_proven': False}
    if status == 'near':
        return result
    if diagnostics is not None:
        diagnostics.enter('saved_apply_intent')
    active_guard()
    # This durable record is intentionally ambiguous: an interruption after
    # it exists may have happened before or after the client received APPLY.
    if checked_operation(record_apply_intent, copy.deepcopy(sample)) is not True:
        raise RuntimeError('saved apply intent not durably recorded')
    active_guard()
    elapsed = time.monotonic() - received_at
    if elapsed < 0 or not math.isfinite(elapsed):
        raise RuntimeError('invalid sample receipt timing')
    if diagnostics is not None:
        diagnostics.enter('saved_apply_once')
    if checked_operation(source.apply_once, sample) is not True:
        raise RuntimeError('saved apply unconfirmed')
    result.update(apply_requested=True, host_receipt_to_apply_seconds_lower_bound=elapsed)
    return result


def run(*, sock, settings, index, baseline, guard, pump, active, host, world,
        identity, verify, verify_process, timeout=90, candidate_indices=None,
        client_motion=False, verify_stopped=None, diagnostics=None,
        diagnostic_timeouts=None, private_long_diagnostic=False, sector_poll=None, sector_stop=None,
        sector_arm=None, sector_incarnation=None, saved_apply_fixture=None, record_apply_intent=None,
        saved_playback_fixture=None, playback_sample_observer=None,
        playback_begin=None, playback_checkpoint_check=None, playback_checkpoint_stop=None, playback_identity_scope=None):
    from authority_paired_playback_evidence import SAMPLE_COUNT, SAMPLE_INTERVAL, DRAIN_SECONDS
    if playback_identity_scope is not None and (saved_playback_fixture is None or not callable(playback_identity_scope)):
        raise ValueError('invalid playback identity scope')
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
    pair_delivery = False
    if 'local_pair' in settings:
        pair = settings['local_pair']
        if (type(pair) is not dict or set(pair) not in ({'nonce', 'index'}, {'nonce', 'index', 'delivery'}) or
                type(pair['index']) is not int or pair['index'] != index or candidate_indices is not None or
                type(pair['nonce']) is not str or not re.fullmatch(r'[0-9a-f]{32}', pair['nonce']) or
                ('delivery' in pair and (pair['delivery'] is not True or client_motion is not True))):
            raise ValueError('local pair differs from the explicit source index')
        pair_delivery = pair.get('delivery') is True
    if (invalid_selection
            or type(identity) is not tuple or len(identity) != 2
            or any(type(value) is not int or value < 1 for value in identity)
            or not callable(verify) or not callable(verify_process)
            or type(client_motion) is not bool
            or type(private_long_diagnostic) is not bool
            or (saved_playback_fixture is None and any(callback is not None for callback in
                (playback_sample_observer, playback_begin, playback_checkpoint_check, playback_checkpoint_stop, playback_identity_scope)))
            or (saved_playback_fixture is not None and
                (saved_playback_fixture != 'recovery_enh_870' or index != 1318 or
                 settings['epoch'] != '4ba7be438ebb04ec5bb85fdb95b5a488' or
                 not client_motion or pair_delivery or 'local_pair' in settings or
                 candidate_indices is not None or saved_apply_fixture is not None or
                 sector_poll is not None or not all(callable(callback) for callback in
                 (playback_sample_observer, playback_begin, playback_checkpoint_check, playback_checkpoint_stop))))
            or (saved_apply_fixture is None and record_apply_intent is not None)
            or (saved_apply_fixture is not None and
                (saved_apply_fixture != 'recovery_enh_870' or index != 1318 or
                 settings['epoch'] != '4ba7be438ebb04ec5bb85fdb95b5a488' or
                 not pair_delivery or not callable(record_apply_intent)))
            or (sector_poll is None and any(value is not None for value in (sector_stop, sector_arm, sector_incarnation)))
            or (sector_poll is not None and (not callable(sector_poll) or not callable(sector_stop) or
                not callable(sector_arm) or type(sector_incarnation) is not str or
                not re.fullmatch(r'[0-9a-f]{32}', sector_incarnation) or not pair_delivery))
            or (private_long_diagnostic and not client_motion)
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
    if private_long_diagnostic and diagnostic_timeouts is None:
        raise ValueError('private long diagnostic requires explicit budgets')
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
                not client_bind < delivery_timeout < source_timeout <= (600 if private_long_diagnostic else 300) or
                delivery_timeout > (480 if private_long_diagnostic else 300) or
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
    sampling_deadline = None

    def check_deadline():
        if time.monotonic() >= deadline or (sampling_deadline is not None and time.monotonic() >= sampling_deadline):
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
            site = diagnostics.guard_call_site()
            started_at = time.monotonic()
            try:
                verify()
            finally:
                elapsed = time.monotonic() - started_at
                diagnostics.full_guard_seconds += elapsed
                diagnostics.record_guard_call('full', site, elapsed)
        check_deadline()
        return True

    def pump_guard():
        with nullcontext() if playback_identity_scope is None else playback_identity_scope():
            return pump_guard_body()

    def pump_guard_body():
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
    if saved_playback_fixture and checked_operation(playback_begin) is not True:
        raise RuntimeError('playback sampling boundary unconfirmed')
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
        checkpoint_check = guard.check if playback_checkpoint_check is None else playback_checkpoint_check
        if diagnostics is None:
            return checkpoint_check() is True
        diagnostics.saved_checkpoint_guard_calls += 1
        site = diagnostics.guard_call_site()
        started_at = time.monotonic()
        try:
            return checkpoint_check() is True
        finally:
            elapsed = time.monotonic() - started_at
            diagnostics.saved_checkpoint_guard_seconds += elapsed
            diagnostics.record_guard_call('saved_checkpoint', site, elapsed)

    staged_samples = []
    sample_received_at = []

    def capture_sample(value):
        # Source IPC calls this before initiating TCP delivery. Rejection
        # after pull() returns would be too late to prevent a client effect.
        if pair_delivery:
            if (type(value) is not dict or value.get('index') != index or value.get('sequence') != 2 or
                    value.get('velocity') is None):
                raise RuntimeError('pair delivery lacks the correlated known-rate sample')
            motion_digest(value)
        if sector_poll is not None:
            if staged_samples or sector_arm() is not True:
                raise RuntimeError('client sector pre-send fence unavailable')
        staged_samples.append(copy.deepcopy(value))
        sample_received_at.append(time.monotonic())
        if diagnostics is not None:
            # Parsed source sample staged locally; not a delivered receipt.
            diagnostics.prevalidated_samples += 1
        return True
    delivery_options = {'private_long_diagnostic': True} if private_long_diagnostic else {}
    delivery = ExperimentalTCPJobDelivery(host, enabled=True, timeout=delivery_timeout, **delivery_options)
    motion_options = {'allow_apply': True} if saved_apply_fixture is not None else {}
    motion = ExperimentalTCPMotion(delivery, enabled=True, **motion_options)
    selected_recipient = None
    if client_motion:
        if sector_poll is not None:
            if (len(world.session.ready_players) != 1 or
                active.participant.handle != world.session.ready_players[0][0] or
                active.participant._sector_incarnation != sector_incarnation):
                raise RuntimeError('client sector participant unavailable')
            if checked_operation(delivery.bind_test_incarnation, active.participant.handle,
                                 sector_incarnation, enabled=True) is not True:
                raise RuntimeError('client sector participant binding unconfirmed')
        members = delivery.membership()
        if len(members) != 1 or len(world.session.ready_players) != 1:
            raise RuntimeError('exactly one admitted motion recipient required')
        handle = world.session.ready_players[0][0]
        if members[0]['id'] != 'peer_' + str(handle):
            raise RuntimeError('motion recipient differs from admitted client')
        selected_recipient = copy.deepcopy(members[0])
        if sector_poll is not None and selected_recipient['incarnation'] != sector_incarnation:
            raise RuntimeError('client sector incarnation differs from participant')

    def select_recipients(_sample, members):
        if not client_motion:
            return []
        if tuple(members) != (selected_recipient,):
            raise RuntimeError('diagnostic motion recipient changed')
        return [copy.deepcopy(selected_recipient)]

    if diagnostics is not None:
        diagnostics.enter('bind_source')
    binding_options = {} if diagnostic_timeouts is None else {'bind_timeout': source_bind}
    if private_long_diagnostic:
        binding_options['private_long_diagnostic'] = True
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
    required_samples = SAMPLE_COUNT if saved_playback_fixture else (1 if pair_delivery else 2)
    if saved_playback_fixture:
        sampling_deadline = min(deadline, time.monotonic() + 15)
    for _ in range(required_samples * 4 if saved_playback_fixture else (1 if pair_delivery else 20)):
        next_pull_at = time.monotonic() + (SAMPLE_INTERVAL if saved_playback_fixture else .1)
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
                if pair_delivery and (received['index'] != index or received['sequence'] != 2 or
                                      received['velocity'] is None):
                    raise RuntimeError('pair delivery lacks the correlated known-rate sample')
                track_key = (settings['epoch'], settings['generation'], index)
                track = motion._tracks.get(track_key)
                recipient_key = (selected_recipient['id'], selected_recipient['incarnation'])
                expected_receipt = (received['sequence'], motion_digest(received))
                if track is None or track['peer_samples'].get(recipient_key) != expected_receipt:
                    raise RuntimeError('motion receipt digest not recorded for client')
                if diagnostics is not None:
                    diagnostics.confirmed_client_receipts += 1
            samples.append(staged_samples[-1])
            if saved_playback_fixture and checked_operation(playback_sample_observer, copy.deepcopy(samples[-1])) is not True:
                raise RuntimeError('playback sample observation unconfirmed')
            if diagnostics is not None:
                diagnostics.samples_received = len(samples)
            if len(samples) == required_samples:
                break
        elif received is not None:
            raise RuntimeError('uncaptured motion receipt')
        elif diagnostics is not None:
            diagnostics.empty_pulls += 1
        if saved_playback_fixture:
            while time.monotonic() < next_pull_at:
                active_guard()
                time.sleep(min(.05, max(0, next_pull_at-time.monotonic())))
        else:
            time.sleep(.1)
    if len(samples) != required_samples:
        raise RuntimeError('required server source samples unavailable')
    sampling_deadline = None
    if sector_poll is not None:
        # The receipt above belongs to this already admitted incarnation. The
        # local owner starts its read only after sending the correlated BOUND.
        def receipt_is_current():
            track = motion._tracks.get((settings['epoch'], settings['generation'], index))
            peer_key = (selected_recipient['id'], selected_recipient['incarnation'])
            return track is not None and track['peer_samples'].get(peer_key) == expected_receipt
        while True:
            active_guard()
            if tuple(delivery.membership()) != (selected_recipient,) or not receipt_is_current():
                raise RuntimeError('client sector participant changed')
            observed = checked_operation(sector_poll, copy.deepcopy(selected_recipient), expected_receipt)
            active_guard()
            if tuple(delivery.membership()) != (selected_recipient,) or not receipt_is_current():
                raise RuntimeError('client sector participant changed')
            if observed is not None:
                if type(observed) is not str or not re.fullmatch(r'[A-Za-z0-9_]{1,128}', observed):
                    raise ValueError('invalid client sector observation')
                break
            time.sleep(.05)
    apply_observation = None
    if saved_apply_fixture is not None:
        apply_observation = perform_saved_apply(source, samples[0], sample_received_at[0],
            active_guard=active_guard, checked_operation=checked_operation,
            record_apply_intent=record_apply_intent, diagnostics=diagnostics)
    if diagnostics is not None:
        diagnostics.enter('stop_source')
    if checked_operation(source.stop_remote) is not True:
        raise RuntimeError('source stop unconfirmed')
    active_guard()
    if saved_playback_fixture:
        # Keep both games running. No new source sample is dispatched during
        # the existing client's hard-age/readback interval before its STOP.
        silence_until = time.monotonic() + DRAIN_SECONDS
        while time.monotonic() < silence_until:
            active_guard()
            time.sleep(min(.05, max(0, silence_until-time.monotonic())))
    if diagnostics is not None:
        diagnostics.enter('stop_checkpoint_guard')
    checkpoint_stop = guard.stop if playback_checkpoint_stop is None else playback_checkpoint_stop
    if checked_operation(checkpoint_stop) is not True:
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
        if sector_stop is not None and checked_operation(sector_stop) is not True:
            raise RuntimeError('client sector stop unconfirmed')
        if stopped_source() is not True:
            raise RuntimeError('source fence changed after client stop')
    if diagnostics is not None:
        diagnostics.enter('close_source')
    checked_operation(source.close)
    public_fields = ('sequence', 'sector_macro', 'source_time', 'x', 'y', 'z', 'velocity')
    public_samples = [{key: sample[key] for key in public_fields} for sample in samples]
    if diagnostics is not None:
        diagnostics.enter('complete')
    result = {
        'index': index,
        'candidate_selected': candidate_indices is not None,
        'candidate_is_reservation': False,
        'samples': public_samples,
        'source_stopped_before_disconnect': True,
        'server_only': not client_motion,
        'client_motion_receipts_confirmed': client_motion,
        'client_worker_stop_confirmed': client_motion,
        'client_receipt_sample_sha256': [motion_digest(sample) for sample in samples] if client_motion else [],
        'client_motion_proven': False,
        'client_motion_visible_proven': False,
        'smooth_motion_proven': False,
        'cross_process_identity_proven': False,
    }
    if pair_delivery:
        result['pair_delivery'] = True
        result['pair_sample_velocity_present'] = public_samples[0]['velocity'] is not None
    else:
        result['second_sample_velocity_present'] = public_samples[1]['velocity'] is not None
    if apply_observation is not None:
        result['saved_apply'] = apply_observation
    if saved_playback_fixture:
        result['saved_playback'] = {'fixture': saved_playback_fixture,
                                  'source_sample_count': len(samples),
                                  'enrollment_sequence': 1,
                                  'silence_before_client_stop_seconds': DRAIN_SECONDS}
    return result
