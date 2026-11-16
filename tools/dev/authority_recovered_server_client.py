"""Opt-in one-client diagnostic inside the recovered server's owner thread.

Caller owns the global X4 lock, both process records, server and its cleanup.
This module does not launch on import and is Linux/loopback-only. After the
bounded first connection ends, the caller may continue its normal accept loop.
Neither Windows, internet, gameplay nor exact bytes consumed by X4 are proven.
"""
from pathlib import Path
import re
import socket
import time

import authority_recovered_remote_load_pair_live as combined
import authority_recovery_tcp_join_live as recovery
from authority.marker_evidence import verify_saved_marker


class ServerClient(combined.RecoveredRemoteParticipant):
    """Reuse the paired runner without ever closing the server's control."""
    cancel_check = None

    def pump_loading(self):
        if self.cancel_check is not None: self.cancel_check()
        result = super().pump_loading()
        if self.cancel_check is not None: self.cancel_check()
        return result

    def enroll(self, epoch, deadline):
        """Preserve enrollment validation while checking diagnostic cancellation."""
        if self.cancel_check is None:
            return super().enroll(epoch, deadline)
        if self.fault or self.peer is not None:
            raise RuntimeError('participant unavailable or already enrolled')
        if not isinstance(epoch, str) or not re.fullmatch(r'[0-9a-f]{32}', epoch):
            raise ValueError('invalid world epoch')
        self.epoch = epoch
        expected = f'HELLO|{self.lease}|{epoch}'.encode('ascii')
        try:
            while time.monotonic() < deadline:
                self.cancel_check()
                try: data, peer = self.sock.recvfrom(769)
                except socket.timeout: continue
                self.cancel_check()
                if data == expected and peer[0] == '127.0.0.1':
                    self.peer = peer
                    return
            raise TimeoutError('participant enrollment timed out')
        except BaseException:
            self.fault = True
            raise

    def cleanup_diagnostic(self):
        self._active_check = None
        errors = []
        for helper in reversed(self.helpers):
            try: helper.stop()
            except BaseException as error: errors.append(error)
        for name in ('remote_ipc', 'ipc', 'client_tcp', 'second', 'sock'):
            obj = getattr(self, name, None)
            if obj is not None:
                try: obj.close()
                except BaseException as error: errors.append(error)
                else: setattr(self, name, None)
        self.fault = True
        if errors:
            raise RuntimeError('diagnostic helper or socket cleanup unconfirmed') from errors[0]
        return True


def record_client_evidence(result, ticket, marker, client_identity, server_identity):
    """Record only noncredential correlation data after final checks succeed."""
    fields = recovery.base.client.FIELDS
    if (type(ticket) is not dict or set(ticket) != set(fields) or type(marker) is not str or
            any(type(identity) is not tuple or len(identity) != 2 or
                any(type(value) is not int or value <= 0 for value in identity)
                for identity in (client_identity, server_identity)) or client_identity == server_identity):
        raise ValueError('invalid diagnostic correlation data')
    result.update(client_ticket={field: ticket[field] for field in fields},
                  client_loaded_marker=marker,
                  client_checkpoint_id=ticket['checkpoint_id'],
                  client_checkpoint_sha256=ticket['sha256'],
                  client_x4_pid=client_identity[0], client_x4_start_ticks=client_identity[1],
                  server_x4_pid=server_identity[0], server_x4_start_ticks=server_identity[1],
                  client_final_log_and_inputs_verified=True,
                  client_owned_process_stopped=True)


def confirmed_baseline(world, expected=None):
    """Require the current paused baseline to agree with the confirmed store."""
    state = world.session
    if (state.state != 'paused' or state.pending is not None or state.save_required or
            state.baseline_id is None or world._baseline is None):
        raise RuntimeError('join baseline is not confirmed and paused')
    saved = world._store.latest_marked_confirmed()
    if (world._baseline != (state.baseline_id, saved) or world._store.latest() != saved or
            (expected is not None and saved != expected)):
        raise ValueError('join baseline differs from confirmed checkpoint')
    return saved


def prepare_join_baseline(host, world, deadline, check, expected=None):
    """Complete the join's pending pause/save, or reuse its paused baseline."""
    while world.session.pending is not None:
        recovery.marked.remaining(deadline)
        check()
        if world.session.pending.operation not in ('pause', 'save'):
            raise RuntimeError('unexpected operation while preparing diagnostic join')
        host.tick(min(.1, recovery.marked.remaining(deadline)))
        check()
    return confirmed_baseline(world, expected)


def verify_join_offer(ticket, marker, baseline):
    if (ticket['checkpoint_id'] != baseline.checkpoint_id or ticket['sha256'] != baseline.sha256 or
            marker != baseline.marker):
        raise ValueError('offered checkpoint differs from confirmed join baseline')


def settle_departure(host, world, control, peer, deadline, check, ticket, marker):
    """Observe EOF and require a fresh marked save before another client."""
    if peer not in control._peers:
        raise RuntimeError('diagnostic peer disappeared before EOF observation')
    recovery.tcp.await_eof(peer, deadline, check)
    while True:
        recovery.marked.remaining(deadline)
        check()
        if (not control._peers and not world.session.players and
                world.session.pending is None and world.session.state == 'paused'):
            break
        host.tick(min(.1, recovery.marked.remaining(deadline)))
        check()
    saved = confirmed_baseline(world)
    if (saved.checkpoint_id == ticket['checkpoint_id'] or saved.marker == marker or
            world._load_offers or world._offers.names):
        raise ValueError('departure did not produce a fresh unoffered checkpoint')
    with world._offers.service.lock:
        if world._offers.service.offered:
            raise ValueError('file offers remain after diagnostic departure')
    if verify_saved_marker(saved, saved.marker, script_name='X4AuthorityCheckpointMarker',
                           cue_name='MarkerState') is not True:
        raise ValueError('departure checkpoint marker not verified')
    check()
    return saved



class ActiveClient:
    """Retained diagnostic with explicit owner-driven finalization."""
    def __init__(self, participant, result, finish):
        self.participant, self.result, self._finish = participant, result, finish
        self._finished = False

    def finish(self):
        if self._finished: raise RuntimeError('diagnostic already finalized')
        # Never retry a partially completed cleanup as if it had not run.
        self._finished = True
        return self._finish()

def run_one(participant, *, args, out, game, home, uid, steam, auth, user,
            processes, server_proc, server_started, server_identity, checkpoint,
            recovery_target, server_expected, recovery_watch, listener, host, service,
            world, session, control, check_server, server_out=None, expected_baseline=None, cancel_check=None,
            check_base=None):
    """Load one genuine local client, confirm admission/resume and disconnect.

    Must run on the server's owner/main thread; it registers its X4 in the
    caller's process list. The caller MUST run cleanup_diagnostic before owned
    X4 cleanup and must retain the global lock if that cleanup is uncertain.
    """
    base = recovery.base
    if cancel_check is not None and not callable(cancel_check):
        raise ValueError('invalid diagnostic cancellation check')
    if participant.keep_worker and not callable(check_base):
        raise ValueError('retained client requires an independent base guard')
    participant.cancel_check = cancel_check
    deadline = participant.run_deadline
    participant.checkpoint = checkpoint
    participant.target = recovery_target
    participant.server_expected = server_expected
    participant.recovery_watch = recovery_watch
    participant.server_library = (server_out or out)/'case/extensions/x4_lan_lab/native/x4lan_net.so'
    participant.session, participant.control, participant.host = session, control, host
    participant.participants = world._participants
    client_out = out/'client'; client_out.mkdir(mode=0o700)
    case, profile, binds, lock = base.snapshot.prepare_case(client_out, game, home)
    if any((profile/'save').iterdir()): raise ValueError('private client profile not empty')
    participant.client_tcp = socket.create_connection(listener.getsockname(), timeout=min(1, recovery.marked.remaining(deadline)))
    accepted, address = listener.accept()
    if address != participant.client_tcp.getsockname() or address[0] != '127.0.0.1':
        accepted.close(); raise ValueError('unexpected diagnostic peer')
    participant.server_tcp = accepted
    try:
        handle = host.adopt(accepted)
    except BaseException:
        accepted.close()
        raise
    # A later join can reuse the paused, last-disconnect checkpoint.
    baseline = prepare_join_baseline(host, world, deadline, check_server, expected_baseline)
    ticket, target = participant.offer_and_download(world, service, handle, client_out, profile)
    verify_join_offer(ticket, participant.marker, baseline)
    config = base.client.install_probe(case, profile, ticket)
    recovery.marked.identity.inject(case, 'load')
    participant.install(case)
    protected = [config, case/'extensions/x4_lan_lab/ui.xml', profile/'content.xml', profile/'config.xml']
    protected += [case/'extensions/x4_lan_lab/ui'/name for name in
                  ('client_load_barrier.lua', 'x4_client_load_engine.lua', 'authority_download_load_probe.lua')]
    protected += participant.protected(case)
    expected = {path:base.live.sha(path) for path in protected}
    command = base.load.readonly_save_command(case, game, binds, lock, args.display, auth, user, args.seed, target)
    pos = command.index('--die-with-parent')
    for path in protected:
        command[pos:pos] = ['--ro-bind', str(path), str(path)]; pos += 3
    proc, started = base.spawn_owned_gated(command, client_out/'process.log', processes)
    watch = base.client.ReceiptWatch(profile/'engine-output.log', ticket)
    client_identity = None
    result = {'client_admitted':False, 'exact_loaded_file_proven':False}
    while True:
        recovery.marked.remaining(deadline)
        check_server()
        actual = base.client.game_identity(proc, started, game)
        if actual is not None:
            if client_identity is not None and actual != client_identity: raise RuntimeError('client X4 changed')
            client_identity = actual
        elif client_identity is not None: raise RuntimeError('client X4 disappeared')
        if base.live.steam_identity(home, uid) != steam: raise RuntimeError('Steam identity changed')
        if any(base.live.sha(path) != digest for path, digest in expected.items()):
            raise ValueError('client protected configuration changed')
        participant.pump_loading()
        caught_up = watch.poll()
        if watch.stage and client_identity is None: raise RuntimeError('receipt without owned client X4')
        if caught_up and watch.stage == 2:
            if base.live.sha(target) != ticket['sha256']: raise ValueError('client staged save changed')
            def client_context(check):
                check()
                return base.check_live_context(deadline=deadline, server_proc=server_proc,
                    server_started=server_started, server_identity=server_identity, client_proc=proc,
                    client_started=started, client_identity=client_identity, game=game, home=home,
                    uid=uid, steam=steam, target=target, ticket=ticket, expected=expected)
            def check_protected(): return client_context(check_server)
            def active_protected(): return client_context(check_base)
            original_accept = session.accept
            try:
                participant.on_ready(world=world, handle=handle, ticket=ticket, target=target,
                    server_identity=server_identity, server_proc=server_proc, server_started=server_started,
                    client_identity=client_identity, client_proc=proc, client_started=started,
                    game=game, out=out, deadline=deadline, result=result, check_protected=check_protected,
                    active_check_protected=active_protected if participant.keep_worker else None)
            finally:
                # TCPMarkedParticipant temporarily wraps accept with a guard for
                # this particular client. Never leak that guard to later joins.
                session.accept = original_accept
            if (result.get('client_admitted') is not True or
                    result.get('native_server_and_client_resume_confirmed') is not True or
                    result.get('tcp_claim_used') is not True or
                    (result.get('helper_active') is not True if participant.keep_worker
                     else result.get('helper_clean_exit') is not True)):
                raise RuntimeError('diagnostic admission or participant resume not confirmed')
            def finish():
                # The supervisor removes this client from its aggregate first.
                # Reap helpers before X4 and keep the X4 registered on uncertainty.
                participant.cleanup_diagnostic()
                remaining = base.snapshot.stop_owned(proc, started)
                if remaining: raise RuntimeError('diagnostic client X4 stop unconfirmed')
                matches = [index for index, record in enumerate(processes)
                           if len(record) == 2 and record[0] is proc and record[1] == started]
                if len(matches) != 1: raise RuntimeError('diagnostic process registration changed')
                del processes[matches[0]]
                check_server()
                if (base.live.sha(target) != ticket['sha256'] or
                        any(base.live.sha(path) != digest for path, digest in expected.items())):
                    raise ValueError('final client inputs changed')
                relative_log = Path('case/home/.config/EgoSoft/X4/45841/engine-output.log')
                participant.verify_logs(out/'server'/relative_log, out/'client'/relative_log, ticket, participant.marker)
                check_server()
                participant.redact()
                participant.config = None
                record_client_evidence(result, ticket, participant.marker, client_identity, server_identity)
                return result
            if participant.keep_worker:
                participant.check_active()
                return ActiveClient(participant, result, finish)
            return finish()
        time.sleep(.1)
