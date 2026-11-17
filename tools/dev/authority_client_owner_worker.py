#!/usr/bin/env python3
"""Private Linux diagnostic child for a single client-owner load and session.

The supervisor owns both X4 processes, their protected files and the meaning of
all observed events. It gives this child connected loopback TCP, an inherited
bound UDP socket and private Unix IPC. The supervisor alone may use UDP until
it has enrolled and paused X4, closed its copy, and sent the activation frame.
Thereafter this child owns TCP and UDP until STOP. No socket is passed onward.

This opt-in load-only experiment does not start X4, observe X4 logs, establish
process ownership, prove an exact loaded file, or provide Windows integration.
The supervisor must guard X4 process identity, protected files, ordered logs,
TLS and host state continuously, including throughout a blocking claim. This
child checks its process context only around the claim, not during the wait.
It cannot retract an already sent claim: on failure, admission is indeterminate.
The supervisor must immediately fence and reap this child before releasing any
X4 process or lock if an outcome is uncertain. STOP also requires the supervisor
to have confirmed the specific resume receipt and a quiet host; the child's
receipt check alone does not establish which command was confirmed.
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
from authority.client_save_staging import copy_offered_save
from authority.experimental_client_owner import ExperimentalClientOwner
from authority.load_messages import MAX_INTEGER
from authority.trusted_load_messages import encode_bound_offer
from authority_tcp_native_worker import (
    GuardedParticipant, check_process, event, parse_json, read_line, send_frame,
    verify_sockets,
)

_HEX = re.compile(r'[0-9a-f]{32}\Z')
_MAX_CONFIG = 16384


def _finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _initial_config(value):
    fields = {'file_port', 'file_token', 'deadline', 'download', 'target'}
    if type(value) is not dict or set(value) != fields:
        raise ValueError('invalid initial configuration')
    now = time.monotonic()
    if (type(value['file_port']) is not int or not 1 <= value['file_port'] <= 65535 or
            type(value['file_token']) is not str or not _HEX.fullmatch(value['file_token']) or
            not _finite_number(value['deadline']) or not now < value['deadline'] < now + 3600 or
            type(value['download']) is not str or type(value['target']) is not str):
        raise ValueError('invalid load endpoint or deadline')
    target = Path(value['target'])
    if target.name != 'save_009.xml.gz' or not target.parent.is_dir() or any(target.parent.iterdir()):
        raise ValueError('empty private save directory required')
    return value


def _activation_config(value, bound, deadline):
    fields = {'command', 'attempt', 'marker', 'load_requested', 'paused', 'epoch', 'handle',
              'lease', 'udp_peer', 'udp_next_id', 'controller_timeout', 'client_process'}
    if type(value) is not dict or set(value) != fields or value['command'] != 'activate':
        raise ValueError('invalid activation frame')
    peer = value['udp_peer']
    if (value['attempt'] != bound.offer.attempt_id or value['marker'] != bound.marker or
            value['load_requested'] is not True or value['paused'] is not True or
            value['epoch'] != bound.offer.world_epoch or
            type(value['handle']) is not int or value['handle'] != bound.offer.connection_handle or
            type(value['lease']) is not str or not _HEX.fullmatch(value['lease']) or
            type(peer) is not list or len(peer) != 2 or peer[0] != '127.0.0.1' or
            type(peer[1]) is not int or not 1 <= peer[1] <= 65535 or
            type(value['udp_next_id']) is not int or not 1 <= value['udp_next_id'] <= MAX_INTEGER or
            not _finite_number(value['controller_timeout']) or not 0 < value['controller_timeout'] <= 300):
        raise ValueError('activation does not match the observed load')
    check_process(value['client_process'])
    return {key: value[key] for key in
            ('epoch', 'handle', 'lease', 'udp_peer', 'udp_next_id', 'controller_timeout', 'client_process')} | {
                'deadline': deadline}


def run(tcp, udp, ipc):
    verify_sockets(tcp, udp, ipc)
    try:
        udp.getpeername()
    except OSError:
        pass
    else:
        raise ValueError('participant UDP must be unconnected')
    ipc.setblocking(False)
    config = _initial_config(parse_json(read_line(ipc, _MAX_CONFIG, time.monotonic() + 30)))
    deadline = config['deadline']
    owner = controller = None
    try:
        owner = ExperimentalClientOwner(tcp, enabled=True, file_host='127.0.0.1',
            file_port=config['file_port'], file_token=config['file_token'], file_slot=1,
            deadline=deadline, io_timeout=300, keepalive_interval=1)
        bound = owner.request_offer()
        downloaded = owner.download(config['download'])
        target = Path(config['target'])
        copy_offered_save(downloaded, target, bound.offer, pump=owner.poll)
        target.chmod(0o400)
        owner.verify_staged(target)
        staged = json.dumps({'event': 'staged', 'offer': encode_bound_offer(bound).decode('ascii')},
                            separators=(',', ':')).encode('ascii')
        send_frame(ipc, staged, deadline, owner.poll)
        activation = parse_json(read_line(ipc, _MAX_CONFIG, deadline, owner.poll))
        settings = _activation_config(activation, bound, deadline)

        def guard():
            if time.monotonic() >= deadline:
                raise TimeoutError('client owner deadline expired')
            check_process(settings['client_process'])
            readable, _, exceptional = select.select([ipc], [], [ipc], 0)
            if readable or exceptional:
                raise RuntimeError('supervisor stopped or disconnected during operation')
            if time.monotonic() >= deadline:
                raise TimeoutError('client owner deadline expired')
            return True

        guard()
        # The supervisor has already verified these events in the same X4
        # process and relinquished its UDP descriptor before this frame.
        owner.load_requested(activation['attempt'])
        owner.loaded_marker(activation['attempt'], activation['marker'])
        owner.paused(activation['attempt'], activation['paused'])
        controller = GuardedParticipant(udp, settings, guard)
        owner.activate(activation['attempt'], controller,
                       participant_timeout=settings['controller_timeout'])
        guard()
        event(ipc, 'active', deadline)
        receipt_sent = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('client owner deadline expired')
            check_process(settings['client_process'])
            readable, _, exceptional = select.select([ipc, tcp], [], [ipc, tcp], min(.05, remaining))
            if exceptional:
                raise RuntimeError('client owner socket exception')
            if ipc in readable:
                if parse_json(read_line(ipc, 256, deadline)) != {'command': 'stop'}:
                    raise ValueError('unexpected supervisor command')
                # Only stop after a complete participant receipt and while no
                # later TCP command or disconnect is observable. The
                # supervisor separately verifies host state before STOP.
                pending, _, bad = select.select([tcp], [], [tcp], 0)
                if not receipt_sent or tcp in readable or pending or bad:
                    raise RuntimeError('participant is not quiet at stop')
                owner.close()
                controller.close()
                controller = None
                event(ipc, 'stopped', deadline)
                return
            if tcp in readable:
                receipt_sent = False
            if owner.poll(0):
                receipt_sent = True
            check_process(settings['client_process'])
    finally:
        try:
            if owner is not None:
                owner.close()
        finally:
            if controller is not None:
                controller.close()


def main(arguments):
    if len(arguments) != 3:
        return 2
    sockets = []
    try:
        descriptors = [int(value) for value in arguments]
        if min(descriptors) < 3 or len(set(descriptors)) != 3:
            return 2
        sockets = [socket.socket(fileno=descriptor) for descriptor in descriptors]
        run(*sockets)
        return 0
    except BaseException:
        if len(sockets) == 3:
            try:
                event(sockets[2], 'failed', time.monotonic() + .25)
            except BaseException:
                pass
        return 1
    finally:
        for connection in sockets:
            connection.close()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
