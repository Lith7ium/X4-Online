#!/usr/bin/env python3
"""Opt-in disposable Linux/Linux TCP + native participant diagnostic.

Imports never launch X4. The cooperative claim is not proof of exact file
consumption; loopback results do not establish Windows, Internet or gameplay.
"""
import argparse
import json
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_trusted_marked_live as marked
from authority.experimental_client_load import ExperimentalClientLoad
from authority.experimental_local_host import ExperimentalLocalHost
from authority.experimental_tcp_control import ExperimentalTCPControl, offer_request
from authority.experimental_tcp_participants import ExperimentalTCPParticipants
from authority.save_transfer import receive
from authority.trusted_load_messages import decode_bound_offer, encode_load_claim
from authority.trusted_marker_load_session import TrustedMarkerLoadSession
from authority_helper_lifecycle import OwnedHelper


def read_line(sock, deadline, maximum=4096):
    """Read one line without consuming any following protocol frame."""
    data = bytearray()
    while len(data) <= maximum:
        sock.settimeout(min(1, marked.remaining(deadline)))
        try: chunk = sock.recv(1)
        except socket.timeout: continue
        if not chunk: raise RuntimeError('private connection closed')
        if chunk == b'\n': return bytes(data)
        data.extend(chunk)
    raise ValueError('private frame too large')


class GuardedTCPParticipants(ExperimentalTCPParticipants):
    """Fence and bound each host-side participant operation at dispatch."""
    def _control(self, operation, handles):
        self.guard()
        old = self._timeout
        self._timeout = min(old, marked.remaining(self.deadline))
        try: result = super()._control(operation, handles)
        finally: self._timeout = old
        self.guard()
        return result


class DeadlineEngine:
    """Bound bridge exchanges by remaining supervisor time, without retries."""
    def __init__(self, engine, deadline): self.engine, self.deadline = engine, deadline
    @property
    def _timeout(self): return self.engine._timeout
    @_timeout.setter
    def _timeout(self, value): self.engine._timeout = value
    def _call(self, operation, *args):
        old = self.engine._timeout
        self.engine._timeout = min(old, marked.remaining(self.deadline))
        try: result = getattr(self.engine, operation)(*args)
        finally: self.engine._timeout = old
        marked.remaining(self.deadline)
        return result
    def pause(self): return self._call('pause')
    def save(self): return self._call('save')
    def resume(self): return self._call('resume')
    def __getattr__(self, name):
        value = getattr(self.engine, name)
        if name == 'checkpoint_published' and callable(value):
            return lambda *args: self._call(name, *args)
        return value


class TCPMarkedParticipant(marked.MarkedParticipant):
    """Private test supervisor; one host owner and one reaped client helper."""
    def __init__(self, deadline):
        super().__init__()
        self.run_deadline = deadline
        self.helpers = []
        self.client_tcp = self.server_tcp = self.ipc = self.second = None
        self.control = self.host = self.participants = None

    def join(self, world):
        marked.remaining(self.run_deadline)
        world._engine = DeadlineEngine(world._engine, self.run_deadline)
        self.session = TrustedMarkerLoadSession(world, enabled=True)
        self.control = ExperimentalTCPControl(self.session, enabled=True, idle_timeout=300)
        self.host = ExperimentalLocalHost(world, self.control, world._offers.service, enabled=True)
        self.participants = GuardedTCPParticipants(self.host, enabled=True, timeout=120)
        world._participants = self.participants
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(('127.0.0.1', 0)); listener.listen(1)
            self.client_tcp = socket.create_connection(listener.getsockname(), timeout=min(1, marked.remaining(self.run_deadline)))
            self.server_tcp, _ = listener.accept()
            return self.host.adopt(self.server_tcp)
        finally:
            listener.close()

    def offer_and_download(self, world, service, handle, out, profile):
        if any((profile/'save').iterdir()): raise ValueError('private client save directory is not empty')
        self.client_tcp.settimeout(min(1, marked.remaining(self.run_deadline)))
        self.client_tcp.sendall(offer_request())
        while True:
            marked.remaining(self.run_deadline)
            self.control.poll(min(.1, marked.remaining(self.run_deadline)))
            peer = self.control._peers.get(self.server_tcp)
            if peer is None: raise RuntimeError('control peer disconnected')
            if peer['stage'] == 'offered' and not peer['out']: break
        bound = decode_bound_offer(read_line(self.client_tcp, self.run_deadline))
        self.offer, self.marker = bound.offer, bound.marker
        save = world._load_offers[handle].save
        if (bound.offer.connection_handle != handle or bound.offer.checkpoint_id != save.checkpoint_id or
                bound.offer.sha256 != save.sha256 or bound.offer.size != save.size or bound.offer.name != save.name):
            raise ValueError('TCP offer differs from coordinator')
        downloaded = receive('127.0.0.1', service.port, service.token, 1, save, out/'download',
                             retries=0, timeout=min(60, marked.remaining(self.run_deadline)))
        marked.remaining(self.run_deadline)
        target = profile/'save'/marked.base.snapshot.SLOT
        if target.exists() or target.is_symlink(): raise ValueError('client save target appeared')
        downloaded.rename(target); target.chmod(0o400)
        self.client_load = ExperimentalClientLoad(enabled=True, offer=self.offer, expected_marker=self.marker)
        self.client_load.verify_staged(target)
        ticket = {key: getattr(self.offer, key) for key in marked.base.client.FIELDS if key != 'slot'}
        ticket['slot'] = 'save_009'; self.ticket = dict(ticket)
        return ticket, target

    def cleanup_before_owned_processes(self):
        # The base harness invokes this with cancellation signals fenced before
        # any owned X4 process or its lock can be released.
        errors = []
        for helper in reversed(self.helpers):
            try: helper.stop()
            except BaseException as error: errors.append(error)
        for name in ('ipc', 'client_tcp', 'second'):
            conn = getattr(self, name, None)
            if conn is not None:
                try: conn.close()
                except BaseException as error: errors.append(error)
                else: setattr(self, name, None)
        if self.control is not None and not (self.control._closed or self.control._failed):
            try: self.control.close()
            except BaseException as error: errors.append(error)
        if self.server_tcp is not None:
            try: self.server_tcp.close()
            except BaseException as error: errors.append(error)
            else: self.server_tcp = None
        try: self.sock.close()
        except BaseException as error: errors.append(error)
        self.fault = True
        if errors: raise RuntimeError('helper or communication cleanup unconfirmed') from errors[0]
        return True

    def on_ready(self, *, world, handle, ticket, target, server_identity, server_proc, server_started,
                 client_identity, client_proc, client_started, game, out, deadline, result, check_protected):
        deadline = min(deadline, self.run_deadline)
        profile = Path('case/home/.config/EgoSoft/X4/45841/engine-output.log')
        server_log, client_log = out/'server'/profile, out/'client'/profile
        def guard():
            if (time.monotonic() >= deadline or
                    marked.base.client.game_identity(server_proc, server_started, game) != server_identity or
                    marked.base.client.game_identity(client_proc, client_started, game) != client_identity or
                    check_protected() is not True):
                raise RuntimeError('deadline, protected files or owned X4 changed')
            return True
        guard(); marked.observe_logs(server_log, client_log, ticket, self.marker); guard()
        attempt = self.offer.attempt_id
        self.client_load.observe_load_requested(attempt)
        self.client_load.observe_loaded_marker(attempt, self.marker)
        self.client_load.observe_pause(attempt, True)
        claim = self.client_load.make_claim(attempt)
        self.guard, self.deadline, self.handle = guard, deadline, handle
        self.participants.guard, self.participants.deadline = guard, deadline
        self.enroll(ticket['world_epoch'], deadline-1)
        marked.GuardedEngine(world._engine, guard, deadline).pause()
        self.request('pause'); guard()
        marked.observe_logs(server_log, client_log, ticket, self.marker); guard()
        original_accept = self.session.accept
        def guarded_accept(connection, claim_value, *, pre_accept):
            result.update(client_admitted=None, admission_state='indeterminate')
            def combined(): return pre_accept() is True and guard() is True
            outcome = original_accept(connection, claim_value, pre_accept=combined)
            result.update(client_admitted=True, admission_state='accepted', trusted_client_claim=True,
                          exact_loaded_file_proven=False)
            return outcome
        self.session.accept = guarded_accept
        ipc_parent, ipc_child = socket.socketpair()
        self.ipc = ipc_parent
        try:
            st = (game/'X4').stat()
            config = {'version':1, 'claim':encode_load_claim(claim).decode('ascii'),
                      'epoch':ticket['world_epoch'], 'handle':handle, 'lease':self.lease,
                      'udp_peer':list(self.peer), 'udp_next_id':self.next_id,
                      'deadline':deadline, 'controller_timeout':min(120, marked.remaining(deadline)),
                      'client_process':{'pid':client_identity[0], 'start_ticks':client_identity[1],
                                        'exe_dev':st.st_dev, 'exe_ino':st.st_ino}}
            encoded = json.dumps(config, separators=(',', ':')).encode('ascii')+b'\n'
            if len(encoded)>4096: raise ValueError('helper configuration too large')
            helper = OwnedHelper([sys.executable, str(ROOT/'tools/dev/authority_tcp_native_worker.py'),
                                  str(self.client_tcp.fileno()), str(self.sock.fileno()), str(ipc_child.fileno())],
                                 registry=self.helpers, pass_fds=(self.client_tcp.fileno(), self.sock.fileno(), ipc_child.fileno()))
            ipc_child.close()
            # Parent must relinquish both transferred descriptions before exec.
            self.client_tcp.close(); self.client_tcp = None
            self.sock.close()
            self.ipc.settimeout(min(1, marked.remaining(deadline))); self.ipc.sendall(encoded)
            guard(); helper.release(); guard()
            while True:
                guard(); self.control.poll(min(.1, marked.remaining(deadline)))
                peer = self.control._peers.get(self.server_tcp)
                if peer is None: raise RuntimeError('client disconnected during admission')
                if peer['stage']=='admitted': break
            if result.get('client_admitted') is not True: raise RuntimeError('TCP claim not admitted')
            original_engine = world._engine
            world._engine = marked.GuardedEngine(original_engine, guard, deadline)
            try:
                self.participants._timeout = min(120, marked.remaining(deadline))
                result['server_state'] = 'indeterminate'
                self.host.tick(min(.1, marked.remaining(deadline))); guard()
                if world.session.state != 'running': raise RuntimeError('native resume not confirmed')
                if json.loads(read_line(self.ipc, deadline)) != {'event':'active'}:
                    raise RuntimeError('client helper did not become active')
                result.update(server_state='running', native_server_and_client_resume_confirmed=True)
                listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    listener.bind(('127.0.0.1',0)); listener.listen(1)
                    self.second = socket.create_connection(listener.getsockname(), timeout=min(1, marked.remaining(deadline)))
                    accepted, _ = listener.accept()
                    try: self.host.adopt(accepted)
                    except BaseException:
                        accepted.close()
                        raise
                finally: listener.close()
                self.participants._timeout = min(120, marked.remaining(deadline))
                result['server_state'] = 'indeterminate'
                self.host.tick(min(.1, marked.remaining(deadline))); guard()
                if world.session.state != 'saving': raise RuntimeError('native pause not confirmed')
                result.update(server_state='paused', native_server_and_client_pause_confirmed=True,
                              simulated_second_join=True, pending_operation='save')
            finally:
                world._engine = original_engine
            self.ipc.settimeout(min(1, marked.remaining(deadline)))
            self.ipc.sendall(b'{"command":"stop"}\n')
            if json.loads(read_line(self.ipc, deadline)) != {'event':'stopped'}:
                raise RuntimeError('client helper did not stop cleanly')
            if helper.proc.wait(timeout=min(5, marked.remaining(deadline))) != 0:
                raise RuntimeError('client helper failed')
            guard(); result.update(tcp_claim_used=True, tcp_participant_commands_used=True,
                                   helper_clean_exit=True)
        finally:
            ipc_child.close()
            # Repeat in the base cleanup hook if this attempt cannot confirm it.
            for helper in reversed(self.helpers): helper.stop()


def run(args):
    participant = TCPMarkedParticipant(time.monotonic()+args.timeout)
    original = marked.MarkedParticipant
    try:
        marked.MarkedParticipant = lambda: participant
        try:
            result = marked.run(args)
        except BaseException as error:
            # marked.run may fail before taking ownership of the participant.
            try: participant.cleanup_before_owned_processes()
            except BaseException as cleanup: error.add_note('participant cleanup failed: '+str(cleanup))
            try: participant.close()
            except BaseException as cleanup: error.add_note('participant socket cleanup failed: '+str(cleanup))
            raise
    finally:
        marked.MarkedParticipant = original
    result['scope'] = ('two isolated Linux X4 processes; TCP marker claim and participant control; '
                       'simulated second join; no Windows, Internet or gameplay')
    (Path(args.out)/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--display',required=True);parser.add_argument('--timeout',type=float,default=600)
    parser.add_argument('--seed',type=int,default=276944566)
    try: result=run(parser.parse_args())
    except (OSError,ValueError,RuntimeError) as error: parser.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1


if __name__=='__main__': sys.exit(main())
