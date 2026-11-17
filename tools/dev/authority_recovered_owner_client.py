#!/usr/bin/env python3
"""Opt-in Linux recovered-X4 diagnostic using one client-owner child.

The existing supervisor owns X4, validates actual load observations and
fences protected files; this child owns its TCP socket from download to STOP.
Only the load/pause/resume path is supported. No gameplay is established.
"""
import json
import os
from pathlib import Path
import select
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_recovered_server_client as diagnostic
import authority_remote_load_pair_live as remote
from authority.experimental_client_load import ExperimentalClientLoad
from authority.trusted_load_messages import decode_bound_offer
from authority_helper_lifecycle import OwnedHelper
from authority_tcp_native_worker import parse_json, send_frame


def _read_guarded_event(connection, limit, deadline, pump):
    """Read one bounded IPC frame; reject bytes following its newline.

    The new diagnostic protocol never pipelines frames. The pump checks the
    server/client context around every select and recv, including fragments.
    """
    frame = bytearray()
    while True:
        pump()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('owner IPC deadline expired')
        readable, _, exceptional = select.select([connection], [], [connection], min(.1, remaining))
        pump()
        if time.monotonic() >= deadline:
            raise TimeoutError('owner IPC deadline expired')
        if exceptional:
            raise RuntimeError('owner IPC socket exception')
        if not readable:
            continue
        try:
            chunk = connection.recv(min(4096, limit + 2 - len(frame)))
        except BlockingIOError:
            continue
        pump()
        if time.monotonic() >= deadline:
            raise TimeoutError('owner IPC deadline expired')
        if not chunk:
            raise ConnectionError('owner IPC closed')
        frame.extend(chunk)
        if b'\n' in frame:
            message, trailing = frame.split(b'\n', 1)
            if trailing or len(message) > limit:
                raise ValueError('invalid owner IPC framing')
            return bytes(message)
        if len(frame) > limit:
            raise ValueError('owner IPC frame too large')


def _require_fresh_join(checkpoint, ticket, marker):
    """Preserve the recovered-client guard before using the new baseline."""
    if (checkpoint is None or ticket['checkpoint_id'] == checkpoint.checkpoint_id or
            marker == checkpoint.marker):
        raise ValueError('join checkpoint is not fresh relative to recovery source')


class RecoveredOwnerClient(diagnostic.ServerClient):
    """One retained owner child; the outer supervisor retains X4 ownership."""

    def __init__(self, deadline, source_store):
        super().__init__(deadline, source_store, keep_worker=False)
        self._diagnostic_server_guard = None
        self._owner_guard_slot = None
        self._udp_identity = None

    def _check_udp(self):
        expected = self._udp_identity
        if expected is None or self.sock is not expected[0] or self.sock.fileno() != expected[1]:
            raise RuntimeError('supervisor UDP ownership changed')
        info = os.fstat(expected[1])
        if (info.st_dev, info.st_ino) != expected[2]:
            raise RuntimeError('supervisor UDP descriptor changed')

    def offer_and_download(self, world, service, handle, out, profile):
        if not callable(self._diagnostic_server_guard):
            raise RuntimeError('server guard unavailable')
        if any((profile / 'save').iterdir()):
            raise ValueError('private save directory is not empty')
        info = os.fstat(self.sock.fileno())
        self._udp_identity = (self.sock, self.sock.fileno(), (info.st_dev, info.st_ino))
        self.remote_ipc, child = socket.socketpair()
        try:
            self.remote_ipc.setblocking(False)
            descriptors = (self.client_tcp.fileno(), self.sock.fileno(), child.fileno())
            self.remote_helper = OwnedHelper([sys.executable, str(ROOT / 'tools/dev/authority_client_owner_worker.py'),
                *(str(descriptor) for descriptor in descriptors)], registry=self.helpers, pass_fds=descriptors)
            child.close()
            self.client_tcp.close()
            self.client_tcp = None
            target = profile / 'save' / diagnostic.recovery.marked.base.snapshot.SLOT
            config = {'file_port': getattr(self, 'diagnostic_file_port', service.port),
                      'file_token': service.token, 'deadline': remote.remote_owner_deadline(self.run_deadline),
                      'download': str(out / 'download'), 'target': str(target)}
            payload = json.dumps(config, separators=(',', ':')).encode('ascii')
            self.remote_helper.release()
            def pump():
                self._diagnostic_server_guard()
                self._check_udp()
                self.pump_loading()
                self._diagnostic_server_guard()
            send_frame(self.remote_ipc, payload, self.run_deadline, pump)
            message = parse_json(_read_guarded_event(self.remote_ipc, 16384, self.run_deadline, pump))
            if type(message) is not dict or set(message) != {'event', 'offer'} or message['event'] != 'staged':
                raise ValueError('invalid owner staging event')
            bound = decode_bound_offer(message['offer'].encode('ascii'))
            self.offer, self.marker = bound.offer, bound.marker
            saved = world._load_offers[handle].save
            if (bound.offer.connection_handle != handle or bound.offer.checkpoint_id != saved.checkpoint_id or
                    bound.offer.sha256 != saved.sha256 or bound.offer.size != saved.size or
                    bound.offer.name != saved.name):
                raise ValueError('owner offer differs from coordinator')
            self.client_load = ExperimentalClientLoad(enabled=True, offer=self.offer, expected_marker=self.marker)
            self.client_load.verify_staged(target, pump=pump)
            fields = diagnostic.recovery.marked.base.client.FIELDS
            ticket = {key: getattr(self.offer, key) for key in fields if key != 'slot'}
            ticket['slot'] = 'save_009'
            _require_fresh_join(self.checkpoint, ticket, self.marker)
            self.ticket = dict(ticket)
            return ticket, target
        finally:
            child.close()

    def _wait_event(self, expected, deadline, guard, *, pump_control, allow_exit=False):
        def pump():
            guard()
            status = self.remote_helper.proc.poll()
            if status is not None and (not allow_exit or status != 0):
                raise RuntimeError('owner child exited unexpectedly')
            if pump_control:
                self.control.poll(0)
            guard()
        result = parse_json(_read_guarded_event(self.remote_ipc, 512, deadline, pump))
        if result != {'event': expected}:
            raise RuntimeError('unexpected owner child event')

    def on_ready(self, *, world, handle, ticket, target, server_identity, server_proc, server_started,
                 client_identity, client_proc, client_started, game, out, deadline, result, check_protected,
                 active_check_protected=None, active_server_check=None, aggregate_guard_includes_server=False):
        if aggregate_guard_includes_server or active_check_protected is not None or active_server_check is not None:
            raise ValueError('owner diagnostic supports one non-retained client')
        deadline = min(deadline, self.run_deadline)
        base = diagnostic.recovery.marked.base
        relative_log = Path('case/home/.config/EgoSoft/X4/45841/engine-output.log')
        server_log, client_log = out / 'server' / relative_log, out / 'client' / relative_log

        def guard():
            if (time.monotonic() >= deadline or
                    base.client.game_identity(server_proc, server_started, game) != server_identity or
                    base.client.game_identity(client_proc, client_started, game) != client_identity):
                raise RuntimeError('deadline or owned X4 changed')
            if check_protected() is not True:
                raise RuntimeError('protected context changed')
            if (time.monotonic() >= deadline or
                    base.client.game_identity(server_proc, server_started, game) != server_identity or
                    base.client.game_identity(client_proc, client_started, game) != client_identity):
                raise RuntimeError('deadline or owned X4 changed')
            return True

        guard()
        self.verify_logs(server_log, client_log, ticket, self.marker)
        guard()
        attempt = self.offer.attempt_id
        self.client_load.observe_load_requested(attempt)
        self.client_load.observe_loaded_marker(attempt, self.marker)
        self.client_load.observe_pause(attempt, True)
        def pump_loading_guarded():
            guard()
            self.pump_loading()
            guard()
        self.client_load.make_claim(attempt, pump=pump_loading_guarded)
        self.guard, self.deadline, self.handle = guard, deadline, handle
        self.participants.guard, self.participants.deadline = guard, deadline
        original_cancel = self.cancel_check
        self.cancel_check = guard
        try:
            self.enroll(ticket['world_epoch'], deadline - 1)
        finally:
            self.cancel_check = original_cancel
        diagnostic.recovery.marked.GuardedEngine(world._engine, guard, deadline).pause()
        self.request('pause')
        guard()
        self.verify_logs(server_log, client_log, ticket, self.marker)
        guard()
        original_accept = self.session.accept
        def guarded_accept(connection, claim_value, *, pre_accept):
            result.update(client_admitted=None, admission_state='indeterminate')
            def combined():
                return pre_accept() is True and guard() is True
            outcome = original_accept(connection, claim_value, pre_accept=combined)
            result.update(client_admitted=True, admission_state='accepted', trusted_client_claim=True,
                          exact_loaded_file_proven=False)
            return outcome
        self.session.accept = guarded_accept
        try:
            self._check_udp()
            executable = (game / 'X4').stat()
            activation = {'command': 'activate', 'attempt': attempt, 'marker': self.marker,
                'load_requested': True, 'paused': True, 'epoch': ticket['world_epoch'], 'handle': handle,
                'lease': self.lease, 'udp_peer': list(self.peer), 'udp_next_id': self.next_id,
                'controller_timeout': min(120, diagnostic.recovery.marked.remaining(deadline)),
                'client_process': {'pid': client_identity[0], 'start_ticks': client_identity[1],
                                   'exe_dev': executable.st_dev, 'exe_ino': executable.st_ino}}
            self.sock.close()
            self.sock = None
            send_frame(self.remote_ipc, json.dumps(activation, separators=(',', ':')).encode('ascii'), deadline, guard)
            self._wait_event('active', deadline, guard, pump_control=True)
            peer = self.control._peers.get(self.server_tcp)
            if peer is None or peer['stage'] != 'admitted' or result.get('client_admitted') is not True:
                raise RuntimeError('owner claim not admitted')
            original_engine = world._engine
            world._engine = diagnostic.recovery.tcp.GuardedCheckpointEngine(original_engine, guard)
            try:
                self.participants._timeout = min(120, diagnostic.recovery.marked.remaining(deadline))
                result['server_state'] = 'indeterminate'
                slot = self._owner_guard_slot
                if type(slot) is not list or len(slot) != 1 or slot[0] is not None:
                    raise RuntimeError('participant exchange guard unavailable')
                slot[0] = guard
                try:
                    self.host.tick(min(.1, diagnostic.recovery.marked.remaining(deadline)))
                finally:
                    if slot[0] is not guard:
                        raise RuntimeError('participant exchange guard changed')
                    slot[0] = None
                guard()
                if world.session.state != 'running':
                    raise RuntimeError('native resume not confirmed')
                result.update(server_state='running', native_server_and_client_resume_confirmed=True,
                              simulated_second_join=False, pending_operation=None)
                link = getattr(self, 'diagnostic_tls_link', None)
                if link is not None:
                    link.expect_departure()
                send_frame(self.remote_ipc, b'{"command":"stop"}', deadline, guard)
                self._wait_event('stopped', deadline, guard, pump_control=False, allow_exit=True)
                while self.remote_helper.proc.poll() is None:
                    guard()
                    diagnostic.recovery.marked.remaining(deadline)
                    time.sleep(.01)
                guard()
                if self.remote_helper.proc.returncode != 0:
                    raise RuntimeError('owner child did not stop cleanly')
                result.update(tcp_claim_used=True, tcp_participant_commands_used=True, helper_clean_exit=True)
            finally:
                world._engine = original_engine
        finally:
            self.session.accept = original_accept
