#!/usr/bin/env python3
"""Opt-in one-job/one-motion diagnostic worker; no process or listener starts.

All X4/profile lifecycle, PID identities, socket FDs, cleanup and failure
fencing belong to the outer supervisor. TCP checkpoint/admission are synthetic.
"""
import json
import math
from pathlib import Path
import re
import select
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_source_to_tcp_worker as base
import authority_tcp_job_client_live as client_worker
from authority_tcp_native_worker import check_process, parse_json, read_line, send_frame
from authority_source_job_bind import bind_source, authorize_source
from authority_motion_ipc_supervisor import bind_source_motion
from authority.experimental_job_motion_scheduler import ExperimentalJobMotionScheduler
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_motion_pair_evidence import validate_pair
from authority.local_participant_control import LocalParticipantControl

_EXTRA = ('client_motion_lease', 'client_motion_attempt', 'source_motion_lease', 'source_motion_attempt')
_SAVED = ('saved_index', 'saved_baseline', 'saved_sector')
_TOKEN = re.compile(r'[0-9a-f]{32}\Z')


def config(raw):
    all_values = parse_json(raw)
    if type(all_values) is not dict or any((key not in all_values for key in _EXTRA)):
        raise ValueError('missing motion context')
    extras = {key: all_values[key] for key in _EXTRA}
    if any((type(value) is not str or not _TOKEN.fullmatch(value) for value in extras.values())):
        raise ValueError('invalid motion context')
    count = all_values.get('motion_count', 1)
    if type(count) is not int or count not in (1, 2):
        raise ValueError('invalid bounded motion count')
    apply_once = all_values.get('apply_once', False)
    if type(apply_once) is not bool or ('apply_once' in all_values and apply_once is not True):
        raise ValueError('invalid apply opt-in')
    max_samples = all_values.get('preflight_max_samples', 12)
    max_seconds = all_values.get('preflight_max_seconds', 20)
    if (type(max_samples) is not int or not 1 <= max_samples <= 16 or type(max_seconds) not in (int, float)
            or not math.isfinite(max_seconds) or not 1 <= max_seconds <= 30
            or (not apply_once and ('preflight_max_samples' in all_values or 'preflight_max_seconds' in all_values))):
        raise ValueError('invalid preflight budget')
    saved = {key: all_values[key] for key in _SAVED if key in all_values}
    if saved:
        if (set(saved) != set(_SAVED) or type(saved['saved_baseline']) is not int
                or type(saved['saved_index']) is not int
                or not 1 <= saved['saved_index'] <= saved['saved_baseline'] <= 9007199254740991
                or type(saved['saved_sector']) is not str or not base._NAME.fullmatch(saved['saved_sector'])):
            raise ValueError('invalid saved baseline context')
    if apply_once and (not saved or count != 1):
        raise ValueError('one-shot apply requires one saved sample')
    rest = {key: value for key, value in all_values.items()
            if key not in _EXTRA and key not in _SAVED
            and key not in ('motion_count', 'apply_once', 'preflight_max_samples', 'preflight_max_seconds')}
    if 'continuous' in rest or 'max_events' in rest:
        raise ValueError('single job diagnostic required')
    c = base.config(json.dumps(rest, separators=(',', ':'), allow_nan=False).encode())
    names = ('epoch', 'lease', 'attempt', 'generation', 'participant_lease', 'job_epoch',
             'source_lease', 'source_attempt', 'source_control_lease')
    values = [c[key] for key in names] + list(extras.values())
    if len(set(values)) != len(values):
        raise ValueError('motion tokens overlap session context')
    c.update(extras)
    c.update(saved)
    c['motion_count'] = count
    c['apply_once'] = apply_once
    c['preflight_max_samples'] = max_samples
    c['preflight_max_seconds'] = float(max_seconds)
    if saved and saved['saved_sector'] not in c['sectors']:
        raise ValueError('saved sector is not witnessed')
    return c


def run(client_control, client_job, client_motion, source_control, source_job, source_motion, private, c):
    sockets = (client_control, client_job, client_motion, source_control, source_job, source_motion)
    for sock in sockets:
        client_worker.validate_udp(sock)
    if len({sock.getsockname() for sock in sockets}) != len(sockets):
        raise ValueError('distinct local UDP ports required')
    source_identity = dict(c['source_process'])
    job_peer = control_peer = motion_peer = None
    scheduler = None

    def source_guard():
        check_process(source_identity)
        for sock, peer in ((source_job, job_peer), (source_motion, motion_peer)):
            if peer is not None and (sock.getpeername() != peer or
                    not client_worker.socket_owner(peer, sock.getsockname(), source_identity)):
                raise RuntimeError('source UDP ownership changed')
        if control_peer is not None and not client_worker.socket_owner(control_peer, source_control.getsockname(), source_identity):
            raise RuntimeError('source control ownership changed')
        check_process(source_identity)
        return True

    def action(delivery, members, guard):
        nonlocal job_peer, control_peer, motion_peer, scheduler
        source_control.settimeout(0.1)
        expected_control_hello = ('HELLO|' + c['source_control_lease'] + '|' + c['source_world_epoch']).encode('ascii')
        while control_peer is None:
            guard()
            try:
                packet, peer = source_control.recvfrom(769)
            except socket.timeout:
                continue
            if packet != expected_control_hello or not client_worker.socket_owner(peer, source_control.getsockname(), source_identity):
                raise RuntimeError('source control peer unconfirmed')
            control_peer = peer
        remaining = c['deadline'] - time.monotonic()
        if remaining <= 45:
            raise TimeoutError('insufficient motion session budget')
        bound_source = bind_source(source_job, process=source_identity, lease=c['source_lease'],
                                   attempt=c['source_attempt'], epoch=c['job_epoch'], generation=c['generation'],
                                   guard=guard, timeout=min(20, remaining - 40))
        if bound_source is not source_job:
            raise RuntimeError('job source handoff differs')
        job_peer = source_job.getpeername()
        guard()
        authorize_source(source_job, process=source_identity, lease=c['source_lease'], attempt=c['source_attempt'],
                         epoch=c['job_epoch'], generation=c['generation'], guard=guard,
                         timeout=min(10, c['deadline'] - time.monotonic() - 40))
        job_bridge = base.SelectedSourceBridge(delivery, source_job, enabled=True, lease=c['source_lease'],
            attempt=c['source_attempt'], epoch=c['job_epoch'], generation=c['generation'], guard=guard,
            timeout=min(90, c['deadline'] - time.monotonic() - 1), expected_index=c['index'], sectors=c['sectors'])
        motion_delivery = ExperimentalTCPMotion(delivery, enabled=True, allow_apply=c['apply_once'])
        job_event = None
        samples = []
        preflights = []
        saved = 'saved_index' in c
        selection_deadline = [None]

        def bounded_guard():
            guard()
            if selection_deadline[0] is not None and time.monotonic() >= selection_deadline[0]:
                raise TimeoutError('motion preflight budget expired')
            return True

        def validate_sample(value):
            target = c['saved_index'] if saved else job_event['index'] if job_event is not None else None
            sector = c['saved_sector'] if saved else job_event['descriptor']['sector_macro'] if job_event is not None else None
            if target is None or value['index'] != target or value['sequence'] != len(samples) + 1:
                return False
            if value['epoch'] != c['job_epoch'] or value['generation'] != c['generation'] or value['sector_macro'] != sector:
                return False
            if not samples:
                return value['velocity'] is None
            if c['apply_once']:
                previous_sample = samples[-1]
                time_delta = value['source_time'] - previous_sample['source_time']
                if not math.isfinite(time_delta) or time_delta <= 0:
                    return False
                if value['velocity'] is not None:
                    if not 0.02 <= time_delta <= 1:
                        return False
                    for axis in ('x', 'y', 'z'):
                        if not math.isclose(value['velocity'][axis], (value[axis] - previous_sample[axis]) / time_delta,
                                            rel_tol=1e-09, abs_tol=1e-09):
                            return False
            else:
                if c['motion_count'] != 2 or len(samples) != 1:
                    return False
                validate_pair([samples[0], value], epoch=c['job_epoch'], generation=c['generation'], index=target, sector=sector)
            return True

        def saved_guard(epoch, baseline):
            if epoch != c['job_epoch'] or baseline != c['saved_baseline'] or bounded_guard() is not True:
                return False
            readable, _, bad = select.select([source_job], [], [source_job], 0)
            return not readable and (not bad) and (bounded_guard() is True)
        source_bridge = bind_source_motion(source_motion, motion_delivery, process=source_identity,
            lease=c['source_motion_lease'], attempt=c['source_motion_attempt'], epoch=c['job_epoch'],
            generation=c['generation'], guard=bounded_guard, timeout=min(35, c['deadline'] - time.monotonic() - 1),
            validate_sample=validate_sample, saved_baseline=c['saved_baseline'] if saved else None,
            saved_guard=saved_guard if saved else None)
        motion_peer = source_motion.getpeername()
        guard()
        scheduler = ExperimentalJobMotionScheduler(job_bridge, source_bridge, enabled=True)
        control = LocalParticipantControl.__new__(LocalParticipantControl)
        control.sock = source_control
        control.lease = c['source_control_lease']
        control.peer = control_peer
        control.epoch = c['source_world_epoch']
        control.handle = 1
        control.next_id = 1
        control.fault = False
        control.timeout = min(20, c['deadline'] - time.monotonic() - 35)
        if control.timeout <= 0:
            raise TimeoutError('source resume budget expired')
        guard()
        control.resume((1,))
        guard()
        if saved:
            guard()
            scheduler.register_saved(c['saved_index'])
            guard()
        if c['apply_once']:
            selection_deadline[0] = min(c['deadline'] - 5, time.monotonic() + c['preflight_max_seconds'])
        while len(samples) < (c['preflight_max_samples'] if c['apply_once'] else c['motion_count']):
            bounded_guard()
            if saved:
                kind, value = ('motion', scheduler.step_motion_only())
            else:
                kind, value = scheduler.step()
            guard()
            if kind == 'job_snapshot_finished':
                raise RuntimeError('source ended before motion sample')
            if kind == 'job':
                if job_event is not None:
                    raise RuntimeError('unexpected second job in single-job diagnostic')
                if value['index'] != c['index'] or value['sequence'] != 1:
                    raise RuntimeError('unexpected source job')
                job_event = value
            elif value is not None:
                if ((not saved and job_event is None)
                        or value['index'] != (c['saved_index'] if saved else job_event['index'])
                        or value['sequence'] != len(samples) + 1):
                    raise RuntimeError('motion without completed job or out of sequence')
                samples.append(value)
                if c['apply_once']:
                    status = scheduler.preflight(value)
                    bounded_guard()
                    preflights.append(status)
                    if status == 'ready':
                        break
        if saved:
            if c['apply_once']:
                if not preflights or preflights[-1] != 'ready':
                    raise TimeoutError('no suitable preflight sample')
                bounded_guard()
                scheduler.apply_once(samples[-1])
                bounded_guard()
                selection_deadline[0] = None
            if c['motion_count'] == 2:
                samples = validate_pair(samples, epoch=c['job_epoch'], generation=c['generation'],
                                        index=c['saved_index'], sector=c['saved_sector'])
            result = {'event': 'result', 'ok': True, 'tcp_admitted': True,
                      'synthetic_server_checkpoint_and_admission': True, 'saved_baseline_registered': True,
                      'index': c['saved_index'], 'sector_macro': c['saved_sector'], 'checkpoint_identity_proven': False,
                      'frame_identity_proven': False, 'motion_pose_applied': c['apply_once'],
                      'motion_client_bound_buffered': True,
                      'motion_velocity_source': 'position_difference_per_source_game_second',
                      'motion_frame_identity_proven': False}
            if c['apply_once']:
                result['motion_sample'] = samples[-1]
                result['motion_preflight_samples'] = samples
                result['motion_preflight_statuses'] = preflights
            elif c['motion_count'] == 1:
                result['motion_sample'] = samples[0]
            else:
                result['motion_samples'] = samples
            return result
        if c['motion_count'] == 2:
            samples = validate_pair(samples, epoch=c['job_epoch'], generation=c['generation'],
                                    index=job_event['index'], sector=job_event['descriptor']['sector_macro'])
        result = {'event': 'result', 'ok': True, 'tcp_admitted': True, 'tcp_job_receipt': True,
                  'source_md_ack_observed': True, 'client_md_ffi_asserted_by_owner': True,
                  'synthetic_server_checkpoint_and_admission': True, 'source_activation_is_birth': False,
                  'descriptor_atomic': False, 'frame_identity_proven': False, 'event_sequence': job_event['sequence'],
                  'index': job_event['index'], 'sector_macro': job_event['descriptor']['sector_macro'],
                  'macro': job_event['descriptor']['macro'], 'faction': job_event['descriptor']['faction'],
                  'motion_client_bound_buffered': True,
                  'motion_velocity_source': 'position_difference_per_source_game_second',
                  'motion_frame_identity_proven': False}
        if c['motion_count'] == 1:
            result['motion_sample'] = samples[0]
        else:
            result['motion_samples'] = samples
        return result
    try:
        return client_worker.run(client_control, client_job, private, c, None, delivery_action=action,
                                 extra_guard=source_guard, expected_jobs=None, motion_udp=client_motion,
                                 allow_motion_apply=c['apply_once'])
    finally:
        if scheduler is not None and scheduler.state == 'ready':
            scheduler.close()


def main():
    if len(sys.argv) != 8:
        return 2
    private = None
    try:
        client_control, client_job, client_motion, source_control, source_job, source_motion, private = (
            socket.socket(fileno=int(value)) for value in sys.argv[1:])
        c = config(read_line(private, 16384, time.monotonic() + 30))
        result = run(client_control, client_job, client_motion, source_control, source_job, source_motion, private, c)
        send_frame(private, json.dumps(result, separators=(',', ':'), allow_nan=False).encode('ascii'), c['deadline'],
                   lambda: (check_process(c['source_process']), check_process(c['client_process'])))
        return 0
    except BaseException:
        try:
            if private is not None:
                private.sendall(b'{"event":"result","ok":false}\n')
        except BaseException:
            pass
        return 1


if __name__ == '__main__':
    sys.exit(main())
