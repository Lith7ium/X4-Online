"""Opt-in one-client diagnostic inside the recovered server's owner thread.

Caller owns the global X4 lock, both process records, server and its cleanup.
This module does not launch on import and is Linux/loopback-only. After the
bounded first connection ends, the caller may continue its normal accept loop.
Neither Windows, internet, gameplay nor exact bytes consumed by X4 are proven.
"""
from pathlib import Path
import json
import re
import secrets
import select
import socket
import sys
import time

import authority_recovered_remote_load_pair_live as combined
import authority_recovery_tcp_join_live as recovery
import authority_recovery_registry_witness as witness
from authority.marker_evidence import verify_saved_marker
from authority_helper_lifecycle import OwnedHelper
from authority_tcp_native_worker import parse_json, read_line, send_frame

REGISTRY_READER = Path(__file__).resolve().with_name('authority_recovered_registry_reader.py')


class ClientMotionErrorWatch(witness.ErrorWatch):
    """Pin one append-only client log and scan incrementally through exit."""
    TAGS = (
        b'[X4LAN] AUTH_RECOVERED_CLIENT_MOTION ERROR',
        b'[X4LAN] AUTH_PARTICIPANT ERROR',
        b'Error while executing onEvent script for event: X4AuthoritySavedBaselineMotionBind.Result.',
        b'Error while executing onEvent script for event: X4AuthorityReplicaMotionBind.Result.',
    )

    def poll(self):
        try:
            super().poll()
        except ValueError as error:
            raise ValueError('client motion log fault or replacement') from error
        return True


class ServerClient(combined.RecoveredRemoteParticipant):
    """Reuse the paired runner without ever closing the server's control."""
    cancel_check = None

    def prepare_client_motion(self, case, profile, status, request, ticket):
        """Install one private, bounded candidate probe before protected binds."""
        import authority_recovered_client_motion_install as motion_install

        if (not self.keep_worker or self.motion_sock is not None or self.motion_worker_config is not None or
                type(request) is not dict or set(request) != {'indices', 'generation', 'timeout'} or
                type(ticket) is not dict):
            raise ValueError('invalid retained client motion request')

        excluded_tokens = {self.lease, ticket['world_epoch'], ticket['attempt_id'],
                           status[1], request['generation']}

        def fresh_token():
            token = secrets.token_hex(16)
            while token in excluded_tokens:
                token = secrets.token_hex(16)
            excluded_tokens.add(token)
            return token

        motion_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            motion_socket.bind(('127.0.0.1', 0))
            settings = {
                'port': motion_socket.getsockname()[1],
                'indices': request['indices'],
                'generation': request['generation'],
                'timeout': request['timeout'],
                'lease': fresh_token(),
                'attempt': fresh_token(),
                'nonce': fresh_token(),
                'router_generation': fresh_token(),
            }
            installation = motion_install.install(case, profile, status, settings)
        except BaseException:
            motion_socket.close()
            raise
        self.motion_sock = motion_socket
        self._pin_motion_socket()
        self.motion_installation = installation
        self.motion_worker_config = {
            key: settings[key] for key in ('lease', 'attempt', 'generation', 'timeout')
        }
        self.motion_worker_config['epoch'] = status[1]
        return list(installation.paths)

    def redact(self):
        errors = []
        installation = getattr(self, 'motion_installation', None)
        if installation is not None:
            try:
                installation.redact()
            except BaseException as error:
                errors.append(error)
            else:
                self.motion_installation = None
        try:
            super().redact()
        except BaseException as error:
            errors.append(error)
        if errors:
            raise BaseExceptionGroup('client config redaction failed', errors)

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
        for resource in reversed(getattr(self,'guard_resources',[])):
            try: resource._cleanup()
            except BaseException as error: errors.append(error)
        for helper in reversed(self.helpers):
            try: helper.stop()
            except BaseException as error: errors.append(error)
        for name in ('remote_ipc', 'ipc', 'client_tcp', 'second', 'sock', 'motion_sock'):
            obj = getattr(self, name, None)
            if obj is not None:
                try:
                    if name=='ipc':self._close_owned_motion_ipc()
                    elif name=='motion_sock':self._close_owned_motion_socket()
                    else:obj.close()
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


def client_registry_enabled(args):
    return (getattr(args, 'registry_status', False) is True or getattr(args, 'registry_enroll', False) is True
            or getattr(args, 'registry_witness_join', False) is True)


def read_registry_while_pumping(participant, baseline, deadline, check):
    """Pump TCP while a pidfd-owned, terminable helper inspects a checkpoint."""
    check()
    parent, child = socket.socketpair()
    helper = None
    try:
        parent.setblocking(False)
        helper = OwnedHelper([sys.executable, str(REGISTRY_READER), str(child.fileno())],
                             registry=participant.helpers, pass_fds=(child.fileno(),))
        child.close()
        config = {key: str(getattr(baseline, key)) if key == 'path' else getattr(baseline, key)
                  for key in ('checkpoint_id','path','sha256','size','marker')}
        payload = json.dumps(config, separators=(',', ':'), ensure_ascii=True).encode('ascii')
        if len(payload) > 4096: raise ValueError('registry reader configuration too large')
        helper.release()
        def pump():
            recovery.marked.remaining(deadline)
            participant.pump_loading()
        send_frame(parent, payload, deadline-1, pump)
        response = parse_json(read_line(parent, 512, deadline-1, pump))
        if type(response) is not dict or set(response) != {'status'} or type(response['status']) is not list:
            raise ValueError('invalid registry reader response')
        status = response['status']
        if status == ['uninitialized']:
            result = ('uninitialized',)
        elif (len(status) == 4 and status[0] == 'ready' and type(status[1]) is str and
              re.fullmatch(r'[0-9a-f]{32}', status[1]) and type(status[2]) is int and
              1 <= status[2] <= 200000 and type(status[3]) is str and re.fullmatch(r'[0-9a-f]{64}', status[3])):
            result = tuple(status)
        else:
            raise ValueError('invalid registry status from reader')
        while helper.proc.poll() is None:
            pump()
            select.select([], [], [], min(.05, recovery.marked.remaining(deadline)))
        if helper.proc.returncode != 0: raise RuntimeError('registry reader failed')
    finally:
        child.close(); parent.close()
        if helper is not None: helper.stop()
    check()
    return result


class WitnessGuardPump:
    """Switch once from admission pumping to non-reentrant active checks."""
    def __init__(self,participant,deadline):
        self.participant=participant;self.deadline=deadline;self.phase='admission'
        self.active_guard=None;self.host=None;self.busy=False

    def activate(self, *, host, guard):
        if self.phase!='admission' or self.busy or not callable(guard):
            self.phase='failed';raise RuntimeError('guard pump switch unavailable')
        self.host=host;self.active_guard=guard;self.phase='active'

    def __call__(self):
        if self.busy or self.phase not in ('admission','active'):
            self.phase='failed';raise RuntimeError('guard pump reentered or unavailable')
        self.busy=True;phase=self.phase
        try:
            recovery.marked.remaining(self.deadline)
            if phase=='admission':self.participant.pump_loading()
            else:
                control=self.host._control
                owned=self.host._busy is False and control._reader_lease is None
                if owned:
                    control._reader_free();lease=object();control._reader_lease=lease;self.host._busy=True
                else:
                    lease=control._reader_lease
                    if self.host._busy is not True or lease is None:
                        raise RuntimeError('active guard TCP fence unavailable')
                try:
                    if self.active_guard() is not True:raise RuntimeError('active guard unavailable')
                finally:
                    changed=(self.host._control is not control or self.host._busy is not True or
                             control._reader_lease is not lease)
                    if owned:
                        if control._reader_lease is lease:control._reader_lease=None
                        self.host._busy=False
                    if changed:raise RuntimeError('active guard changed TCP ownership')
            if self.phase!=phase:raise RuntimeError('guard pump context changed')
        except BaseException:
            self.phase='failed';raise
        finally:self.busy=False


def prepare_witness_guard(participant, world, baseline, deadline, check):
    """Initialize a fully validated saved-witness guard while admission pumps.

    This is a private retained-client facility. Before making guard calls in
    a running source reader lease the caller MUST replace pump with a
    non-reentrant process/context fence; no live source is started here.
    """
    if participant.keep_worker is not True or not callable(check):
        raise ValueError('retained diagnostic and guard required')
    import authority_witness_guard_client
    check()
    pump=WitnessGuardPump(participant,deadline)
    if not hasattr(participant,'guard_resources'):participant.guard_resources=[]
    guard=authority_witness_guard_client.WitnessGuardClient(world._store,baseline,deadline=deadline,
        registry=participant.helpers,pump=pump,cleanup_registry=participant.guard_resources)
    if guard.check() is not True:raise RuntimeError('checkpoint guard unavailable')
    check()
    return guard,pump


def guarded_registry_observation(check, verify):
    """Verify status within the same guarded context used at pre-accept."""
    if check() is not True: raise RuntimeError('client context unavailable')
    if verify is not None:
        if verify() is not True: raise RuntimeError('client registry observation unavailable')
        if check() is not True: raise RuntimeError('client context changed')
    return True


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
            check_base=None, check_server_base=None, witness_guard_ready=None, client_motion=None):
    """Load one genuine local client, confirm admission/resume and disconnect.

    Must run on the server's owner/main thread; it registers its X4 in the
    caller's process list. The caller MUST run cleanup_diagnostic before owned
    X4 cleanup and must retain the global lock if that cleanup is uncertain.
    """
    base = recovery.base
    if cancel_check is not None and not callable(cancel_check):
        raise ValueError('invalid diagnostic cancellation check')
    if participant.keep_worker and (not callable(check_base) or not callable(check_server_base)):
        raise ValueError('retained client requires independent process and server guards')
    if witness_guard_ready is not None and (not callable(witness_guard_ready) or
            not participant.keep_worker or getattr(args,'registry_witness_join',False) is not True):
        raise ValueError('witness guard requires retained witness join')
    if client_motion is not None and (not participant.keep_worker or witness_guard_ready is None):
        raise ValueError('client motion requires retained witness join')
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
    registry_observation = None
    if client_registry_enabled(args):
        import authority_recovered_client_registry as client_registry
        if witness_guard_ready is None:
            status = read_registry_while_pumping(participant, baseline, deadline, check_server)
        else:
            guard,pump=prepare_witness_guard(participant,world,baseline,deadline,check_server)
            witness_guard_ready(guard,baseline,pump)
            status=guard.status
        confirmed_baseline(world, baseline)
        if witness_guard_ready is not None and guard.check() is not True:
            raise RuntimeError('checkpoint changed during admission')
        verify_join_offer(ticket, participant.marker, baseline)
        registry_observation = (client_registry, secrets.token_hex(16), status)
    config = base.client.install_probe(case, profile, ticket)
    recovery.marked.identity.inject(case, 'load')
    participant.install(case)
    protected = [config, case/'extensions/x4_lan_lab/ui.xml', profile/'content.xml', profile/'config.xml']
    protected += [case/'extensions/x4_lan_lab/ui'/name for name in
                  ('client_load_barrier.lua', 'x4_client_load_engine.lua', 'authority_download_load_probe.lua')]
    protected += participant.protected(case)
    if registry_observation is not None:
        client_registry, nonce, status = registry_observation
        protected += client_registry.install(case, nonce, status)
        if getattr(args, 'registry_witness_join', False):
            # Keep the saved witness script present, without asserting that the
            # client's loaded references correspond to the server's objects.
            import shutil
            witness_script = case/'extensions/x4_lan_lab/md/authority_registry_witness.xml'
            if witness_script.exists() or witness_script.is_symlink(): raise ValueError('client witness script already present')
            shutil.copyfile(Path(__file__).resolve().with_name('authority_registry_witness.xml'), witness_script)
            protected.append(witness_script)
        if client_motion is not None:
            for path in participant.prepare_client_motion(case,profile,status,client_motion,ticket):
                if path not in protected:protected.append(path)
    expected = {path:base.live.sha(path) for path in protected}
    motion_watch=ClientMotionErrorWatch(profile/'engine-output.log') if client_motion is not None else None
    if motion_watch is not None:motion_watch.poll()
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
        if motion_watch is not None:motion_watch.poll()
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
            def registry_context(check):
                verify = (lambda: client_registry.verify_log(profile/'engine-output.log', nonce, status, ticket,
                                                             participant.marker)) if registry_observation is not None else None
                value=guarded_registry_observation(lambda: client_context(check), verify)
                if motion_watch is not None:
                    motion_watch.poll();client_context(check)
                return value
            def check_protected(): return registry_context(check_server)
            def active_protected(): return registry_context(check_base)
            if registry_observation is not None:
                check_protected()
                result['client_registry_status'] = {
                    'checkpoint_id': baseline.checkpoint_id, 'checkpoint_sha256': baseline.sha256,
                    'state': status[0], 'epoch': status[1] if len(status) > 1 else None,
                    'count': status[2] if len(status) > 2 else None,
                    'saved_mapping_sha256': status[3] if len(status) > 3 else None,
                    'cross_process_identity_proven': False, 'exact_loaded_file_proven': False}
            original_accept = session.accept
            try:
                participant.on_ready(world=world, handle=handle, ticket=ticket, target=target,
                    server_identity=server_identity, server_proc=server_proc, server_started=server_started,
                    client_identity=client_identity, client_proc=proc, client_started=started,
                    game=game, out=out, deadline=deadline, result=result, check_protected=check_protected,
                    active_check_protected=active_protected if participant.keep_worker else None,
                    aggregate_guard_includes_server=participant.keep_worker,
                    active_server_check=check_server_base if participant.keep_worker else None)
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
                if client_motion is not None and not participant.motion_stop_confirmed:
                    raise RuntimeError('client motion STOP was not confirmed')
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
                if registry_observation is not None:
                    client_registry.verify_log(out/'client'/relative_log, nonce, status, ticket, participant.marker)
                if motion_watch is not None:
                    motion_watch.poll()
                    if motion_watch.identity is None:raise ValueError('client motion log missing')
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
