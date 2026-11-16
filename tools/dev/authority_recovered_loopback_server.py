#!/usr/bin/env python3
"""Run an isolated recovered X4 coordinator with loopback-only client endpoints.

Experimental development entry point. It accepts the recorded recovery fixture
or an explicitly selected, cleanly completed output of this same supervisor.
It never touches normal saves. The X4 process, profile, checkpoint store and
networking are owned by this invocation; no WAN listener is opened.
Actual client loading, gameplay and cross-platform operation are not proven.
"""
import argparse
import json
import math
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import signal
import socket
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_recovery_bridge_live as bridge
import authority_recovery_join_source as source
import authority_recovery_live as recovery
import authority_two_x4_live as owned
import authority_load_live as load
import linux_gate_live as live
import linux_snapshot_capture as snapshot
from authority.checkpoints import CheckpointStore
from authority.experimental_local_host import ExperimentalLocalHost
from authority.experimental_tcp_control import ExperimentalTCPControl
from authority.experimental_tcp_participants import ExperimentalTCPParticipants
from authority.local_control_bridge import LocalControlBridge
from authority.load_messages import _pairs, _reject_constant
from authority.recovery import stage_confirmed_recovery
from authority.save_transfer import SaveOffers
from authority.trusted_marker_load_session import TrustedMarkerLoadSession
from authority.world import WorldCoordinator
from authority_control_cycle_evidence import read_cycle_evidence


def read_evidence(path, limit=65536):
    """Read bounded local evidence, refusing symlinks and in-place changes."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError('invalid source evidence file')
        with os.fdopen(fd, 'rb') as stream:
            fd = -1
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        if (len(data) > limit or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) !=
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
            raise ValueError('source evidence changed')
        return data
    finally:
        if fd >= 0: os.close(fd)


def verify_previous_source(store, checkpoint, profile):
    """Accept only a compatible, cleanly ended local supervisor generation.

    This is local provenance, not authentication or a concurrent-writer fence.
    The caller must own the source and keep its writers and X4 processes stopped.
    stage_confirmed_recovery has independently checked the save's marker.
    """
    origin = store.directory.parent
    if store.directory.name != 'checkpoints': raise ValueError('unsupported source store')
    path = origin/'result.json'
    try:
        result = json.loads(read_evidence(path).decode('utf-8'), object_pairs_hook=_pairs,
                            parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('invalid source supervisor result') from error
    if (type(result) is not dict or type(result.get('supervisor_version')) is not int or result['supervisor_version'] != 1 or
            result.get('success') is not True or result.get('final_world_state') != 'paused' or
            result.get('owned_processes_remaining') != [] or 'cleanup_errors' in result or 'cleanup_error' in result or
            result.get('final_checkpoint_id') != checkpoint.checkpoint_id or
            result.get('final_checkpoint_sha256') != checkpoint.sha256):
        raise ValueError('source supervisor did not end with this confirmed checkpoint')
    if store.latest_marked_confirmed() != checkpoint:
        raise ValueError('source confirmed checkpoint changed')
    if read_evidence(store.directory/'CURRENT',4096) != read_evidence(store.directory/'CONFIRMED',4096):
        raise ValueError('source current checkpoint is not confirmed')
    case = origin/'case'; md = case/'extensions/x4_lan_lab/md'
    if md.is_symlink() or {p.name for p in md.iterdir()} != {'authority_checkpoint_marker.xml','authority_identity_fixture.xml'}:
        raise ValueError('source saved-state scripts differ')
    if read_evidence(case/'home/.config/EgoSoft/X4/45841/content.xml') != read_evidence(Path(profile)/'content.xml'):
        raise ValueError('source and recovery content differ')
    if read_evidence(md/'authority_checkpoint_marker.xml') != read_evidence(ROOT/'src/authority/md/checkpoint_marker.xml'):
        raise ValueError('source marker script differs')
    fixture = read_evidence(md/'authority_identity_fixture.xml')
    if fixture != read_evidence(ROOT/'tools/dev/authority_identity_fixture.xml'):
        raise ValueError('source identity fixture differs')
    if store.latest_marked_confirmed() != checkpoint:
        raise ValueError('source checkpoint changed during verification')
    return fixture


def verify_final_recovery(watch):
    """Drain the owned, closed game's log; reject duplicates or partial lines."""
    while True:
        offset = watch.offset
        if watch.poll(): break
        if watch.offset == offset: raise ValueError('incomplete recovery log')
    if watch.stage != 3: raise ValueError('recovery evidence incomplete')


def settle_shutdown(control, world, store, check):
    """Disconnect clients and settle their last-disconnect pause/save once."""
    control.close()
    while world.session.pending is not None:
        check()
        world.step()
    check()
    if world.session.state != 'paused' or world.session.players:
        raise RuntimeError('world did not settle paused after shutdown')
    if world.session.baseline_id is None:
        return None
    saved = store.latest_marked_confirmed()
    if world._baseline != (world.session.baseline_id, saved):
        raise ValueError('final baseline differs from confirmed checkpoint')
    return saved


def stop_owned_processes(processes, helpers_stopped, errors):
    """Return known survivors or None whenever stopping any process is uncertain."""
    if not helpers_stopped:
        return None
    remaining = []
    uncertain = False
    for proc, started in reversed(processes):
        try:
            if started is None:
                uncertain = True
                if proc.poll() is None: proc.terminate(); proc.wait(timeout=15)
                errors.append('launcher identity unavailable')
            else:
                remaining.extend(snapshot.stop_owned(proc, started))
        except BaseException as error:
            uncertain = True
            errors.append('owned cleanup: '+type(error).__name__)
    return None if uncertain else remaining


def cleanup_diagnostics(diagnostics, errors):
    """Attempt every helper cleanup even if another client's cleanup fails."""
    clean = True
    for diagnostic in reversed(diagnostics):
        try: diagnostic.cleanup_diagnostic()
        except BaseException as error:
            clean = False
            errors.append('diagnostic helper cleanup unconfirmed: '+type(error).__name__)
    return clean


def serve(listener, host, *, deadline, check, should_stop=lambda: False, tick_interval=.1):
    """Accept and pump local peers until deadline, including while world is empty.

    Returns state observations; exceptions fence the caller's entire session.
    The caller owns the listener, host and all cleanup. Timeouts only end this
    development process; they do not assert that a running world was saved.
    """
    if listener.family != socket.AF_INET or listener.getsockname()[0] != '127.0.0.1':
        raise ValueError('loopback listener required')
    if not callable(check) or not callable(should_stop) or not math.isfinite(deadline) or not 0 < tick_interval <= 1:
        raise ValueError('invalid supervisor configuration')
    listener.setblocking(False)
    accepted = 0
    admitted = 0
    admitted_handles = set()
    while time.monotonic() < deadline and not should_stop():
        check()
        # Limit accepts per tick so connection attempts cannot starve X4 actions.
        for _ in range(8):
            try: conn, address = listener.accept()
            except BlockingIOError: break
            try:
                if address[0] != '127.0.0.1':
                    raise ValueError('non-loopback peer')
                host.adopt(conn)
                accepted += 1
            except ValueError:
                conn.close()
            except BaseException:
                conn.close()
                raise
        host.tick(tick_interval)
        for peer in host._control._peers.values():
            if peer['stage'] == 'admitted' and peer['handle'] not in admitted_handles:
                admitted_handles.add(peer['handle'])
                admitted += 1
        # poll() returns immediately without peers: wait for a new connection.
        if not host._control._peers:
            import select
            select.select([listener], [], [], min(tick_interval, max(0, deadline-time.monotonic())))
    check()
    return {'accepted_connections': accepted, 'admitted_connections': admitted}





def verify_diagnostic_context(*, verify_server, active_clients, check_process, check_cancel):
    """Hash server and clients before and after each participant check.

    Each client's active check owns only its own protected inputs. Callbacks
    must raise on failure; this function never retries or resumes an operation.
    """
    check_cancel()
    verify_server()
    for active in tuple(active_clients):
        active.participant.check_active(server_checked=True)
        verify_server()
    check_process()
    check_cancel()

def validate_overlap_identities(first, second):
    """Correlate the three independently tracked Linux X4 process identities."""
    identities = []
    for result in (first, second):
        pairs = []
        for role in ('server', 'client'):
            pair = (result.get(role+'_x4_pid'), result.get(role+'_x4_start_ticks'))
            if any(type(value) is not int or value <= 0 for value in pair):
                raise ValueError('invalid diagnostic X4 identity')
            pairs.append(pair)
        identities.append(pairs)
    if (identities[0][0] != identities[1][0] or
            len({identities[0][0], identities[0][1], identities[1][1]}) != 3):
        raise ValueError('diagnostic X4 identities are not three distinct processes')

def run_overlapping_diagnostics(*, start, active_clients, world, host, control, deadline, verify, clock=None):
    """Own two overlapping diagnostics and settle their ordered departures."""
    import authority_recovered_server_client as client
    if active_clients: raise ValueError('diagnostics must start with an empty active set')
    for index in range(2):
        active = start(index)
        active_clients.append(active)
        verify()
    if (world.session.state != 'running' or len(world.session.ready_players) != 2 or
            len(world.session.players) != 2):
        raise RuntimeError('two active diagnostic participants not confirmed')
    # The remaining participant is guarded during each intentional departure.
    first = active_clients.pop(0)
    first_result = first.finish()
    first_peer = first.participant.server_tcp
    client.recovery.tcp.await_eof(first_peer, deadline, verify)
    while first_peer in control._peers:
        verify(); host.tick(min(.1, client.recovery.marked.remaining(deadline)))
    if (world.session.state != 'running' or len(world.session.players) != 1 or
            len(world.session.ready_players) != 1):
        raise RuntimeError('remaining diagnostic participant did not stay running')
    clock_result = None
    if clock is not None:
        remaining = tuple(world.session.ready_players)
        def check_remaining():
            verify()
            if (world.session.state != 'running' or world.session.pending is not None or
                    tuple(world.session.ready_players) != remaining or len(world.session.players) != 1 or
                    first_peer in control._peers):
                raise RuntimeError('remaining participant changed during clock observation')
        def tick(): host.tick(min(.1, client.recovery.marked.remaining(deadline)))
        clock_result = clock.observe(deadline, tick, check_remaining)
    second = active_clients.pop(0)
    second_result = second.finish()
    baseline = client.settle_departure(host, world, control, second.participant.server_tcp,
        deadline, verify, second_result['client_ticket'], second_result['client_loaded_marker'])
    second_result.update(departure_checkpoint_id=baseline.checkpoint_id,
                         departure_checkpoint_sha256=baseline.sha256,
                         departure_checkpoint_marker=baseline.marker)
    validate_overlap_identities(first_result, second_result)
    result = {'diagnostic_overlap_confirmed':True, 'diagnostic_remaining_session_running':True,
              'diagnostic_overlap_clients':[first_result, second_result]}
    if clock_result is not None: result['diagnostic_remaining_server_clock'] = clock_result
    return result

def run(args):
    if sys.platform != 'linux' or os.geteuid() == 0:
        raise ValueError('unprivileged Linux user required')
    out = snapshot.output_path(args.out)
    source_store = CheckpointStore(load.local_directory(args.store))
    if out.resolve().is_relative_to(source_store.directory.parent) or source_store.directory.parent.is_relative_to(out.resolve()):
        raise ValueError('output and source must be separate')
    game = args.game.resolve(strict=True)
    if live.sha(game/'X4') != live.EXE_SHA or not (game/'extensions').is_dir() or not shutil.which('bwrap'):
        raise ValueError('pinned X4 or bubblewrap unavailable')
    if live.x4_executables(): raise ValueError('another X4 process is running')
    if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?', args.display): raise ValueError('local X11 display required')
    auth = Path(os.environ.get('XAUTHORITY', ''))
    if not auth.is_file() or not os.access(auth, os.R_OK): raise ValueError('readable XAUTHORITY required')
    auth = auth.resolve(strict=True)
    if (not math.isfinite(args.timeout) or not 0 < args.timeout <= 86400 or
            type(args.seed) is not int or not 0 <= args.seed <= 0xffffffff):
        raise ValueError('invalid timeout or seed')
    user = pwd.getpwuid(os.geteuid()); home = Path(user.pw_dir)
    steam = live.steam_identity(home, user.pw_uid)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    operations=[]
    result = {'supervisor_version':1, 'success':False, 'scope':'isolated recovered Linux X4, loopback only; not gameplay or Internet',
              'windows_tested':False, 'internet_tested':False, 'exact_loaded_file_proven':False,
              'engine_operations':operations}
    processes=[]; handlers={}; lockbox=[]; services=[]; sock=listener=control=clock_sock=None
    endpoint=out/'endpoint.json'; deadline=time.monotonic()+args.timeout
    watch=target=checkpoint=expected=None
    diagnostics = []
    active_clients = []
    try:
        case, profile, binds, lock = snapshot.prepare_case(out, game, home)
        stage = out/'staged-profile'; stage.mkdir(mode=0o700)
        checkpoint, staged = stage_confirmed_recovery(source_store, stage)
        if source_store.directory == source.DEFAULT_STORE.resolve():
            fixture = source.verify(source_store.directory, checkpoint, profile)
        else:
            fixture = verify_previous_source(source_store, checkpoint, profile)
        target = profile/'save/save_008.xml.gz'
        if any(target.parent.iterdir()): raise ValueError('new profile save directory not empty')
        os.link(staged, target, follow_symlinks=False); target.chmod(0o400)
        if live.sha(target) != checkpoint.sha256: raise ValueError('recovery save changed')
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('127.0.0.1', 0)); sock.settimeout(.25)
        lease, epoch = secrets.token_hex(16), secrets.token_hex(16)
        protected = bridge.install_probe(case, profile, sock.getsockname()[1], lease, epoch)
        clock = None
        if getattr(args, 'diagnostic_overlap', False):
            import authority_overlap_clock
            clock_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            clock_sock.bind(('127.0.0.1', 0))
            protected.append(authority_overlap_clock.install(case, clock_sock.getsockname()[1]))
            clock = authority_overlap_clock.OverlapClock(clock_sock, lease)
        protected.append(bridge.install_saved_identity_fixture(case, fixture))
        expected = {path:live.sha(path) for path in protected}
        store_path = out/'checkpoints'; store_path.mkdir(mode=0o700)
        store = CheckpointStore(store_path)
        bridge.acquire_lock_with_handlers(handlers, lockbox, user.pw_uid, user.pw_gid)
        stop = [False]
        def request_stop(_number, _frame): stop[0] = True
        for number in handlers: signal.signal(number, request_stop)
        command = load.readonly_save_command(case,game,binds,lock,args.display,auth,user.pw_name,args.seed,target)
        pos = command.index('--die-with-parent')
        for path in protected:
            command[pos:pos] = ['--ro-bind',str(path),str(path)]; pos += 3
        proc, started = owned.spawn_owned_gated(command, out/'process.log', processes)
        identity = None
        watch = recovery.RecoveryWatch(profile/'engine-output.log', checkpoint.marker)
        serving = [False]; recovered = [False]
        def check():
            nonlocal identity
            if stop[0] and not serving[0]: raise InterruptedError('startup cancelled')
            if proc.poll() is not None: raise RuntimeError('owned launcher exited')
            actual = owned.client.game_identity(proc, started, game)
            if actual is not None:
                if identity is not None and actual != identity: raise RuntimeError('owned X4 changed')
                identity = actual
            elif identity is not None: raise RuntimeError('owned X4 disappeared')
            if live.steam_identity(home,user.pw_uid) != steam: raise RuntimeError('Steam identity changed')
            if watch.stage and identity is None: raise RuntimeError('recovery receipt without owned X4')
            if recovered[0]:
                watch.poll()
                if watch.stage != 3: raise ValueError('recovery evidence changed')
        def verify():
            check()
            if identity is None: raise RuntimeError('recovery receipt without owned X4')
            if live.sha(target) != checkpoint.sha256 or any(live.sha(p) != h for p,h in expected.items()):
                raise ValueError('recovery save or protected configuration changed')
            check()
        peer = bridge.activate(sock, watch, lease, epoch, deadline, check, verify)
        recovered[0] = True
        check()
        result.update(source_checkpoint_id=checkpoint.checkpoint_id, source_sha256=checkpoint.sha256,
                      load_marker_observed=True, pause_observed=True)
        adapter = LocalControlBridge(enabled=True, sock=sock, peer=peer, lease=lease, world_epoch=epoch,
            profile=profile, store=store, verify_checkpoint=read_cycle_evidence, timeout=130, marker_required=True)
        service = owned.start_owned_file_service(secrets.token_hex(16), services)
        world = WorldCoordinator(epoch, adapter, store, SaveOffers(service, store))
        session = TrustedMarkerLoadSession(world, enabled=True)
        control = ExperimentalTCPControl(session, enabled=True, idle_timeout=300, keepalive_enabled=True)
        host = ExperimentalLocalHost(world, control, service, enabled=True)
        class GuardedParticipants(ExperimentalTCPParticipants):
            def _exchange(self, conn, peer, others, raw, expected, deadline, check=None, validate_answer=None):
                if check is not None: raise RuntimeError('unexpected nested participant guard')
                return super()._exchange(conn, peer, others, raw, expected, deadline,
                                         check=verify_process, validate_answer=validate_answer)
            def _quiet(self, peers, deadline):
                verify_process(); result = super()._quiet(peers, deadline); verify_process(); return result
        overlap_guard = [None]
        def verify_process():
            if overlap_guard[0] is None: return check()
            return overlap_guard[0]()
        world._participants = GuardedParticipants(host, enabled=True, timeout=120)
        listener=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0)); listener.listen(8)
        # Guard every synchronous engine call, including potentially long save operations.
        original = world._engine
        class GuardedEngine:
            def __getattr__(self, name):
                value = getattr(original, name)
                if name in ('pause','resume','save','checkpoint_published') and callable(value):
                    def call(*args):
                        verify_process(); result = value(*args); verify_process(); operations.append(name); return result
                    return call
                return value
        world._engine = GuardedEngine()
        serving[0] = True
        diagnostic_count = getattr(args, 'diagnostic_clients', None)
        if diagnostic_count is not None and (type(diagnostic_count) is not int or diagnostic_count != 2):
            raise ValueError('only two sequential diagnostic clients are supported')
        if diagnostic_count is not None and getattr(args, 'diagnostic_client', False):
            raise ValueError('choose one diagnostic mode')
        overlap = getattr(args, 'diagnostic_overlap', False)
        if type(overlap) is not bool or (overlap and (getattr(args, 'diagnostic_client', False) or diagnostic_count is not None)):
            raise ValueError('choose one diagnostic mode')
        if overlap:
            import authority_recovered_server_client as diagnostic_client
            def cancelled():
                if stop[0]: raise InterruptedError('diagnostic cancelled')
            def base_overlap():
                # Each retained client's own context checks its X4 and files;
                # the outer aggregate separately verifies the server once.
                cancelled(); check(); cancelled()
            def server_overlap():
                cancelled(); verify(); cancelled()
            def verify_overlap():
                verify_diagnostic_context(verify_server=verify, active_clients=active_clients,
                    check_process=check, check_cancel=cancelled)
            def cancel_overlap(): verify_overlap()
            overlap_guard[0] = verify_overlap
            def start_overlap(index):
                diagnostic = diagnostic_client.ServerClient(deadline, source_store.directory, keep_worker=True)
                diagnostics.append(diagnostic)
                diagnostic_out = out/('overlap-%02d' % (index+1)); diagnostic_out.mkdir(mode=0o700)
                return diagnostic_client.run_one(diagnostic, args=args, out=diagnostic_out, game=game,
                    home=home, uid=user.pw_uid, steam=steam, auth=auth, user=user.pw_name,
                    processes=processes, server_proc=proc, server_started=started, server_identity=identity,
                    checkpoint=checkpoint, recovery_target=target, server_expected=expected,
                    recovery_watch=watch, listener=listener, host=host, service=service, world=world,
                    session=session, control=control, check_server=verify_overlap, check_base=base_overlap,
                    check_server_base=server_overlap,
                    server_out=out, cancel_check=cancel_overlap)
            result.update(run_overlapping_diagnostics(start=start_overlap, active_clients=active_clients,
                world=world, host=host, control=control, deadline=deadline, verify=verify_overlap, clock=clock))
            overlap_guard[0] = None
        if getattr(args, 'diagnostic_client', False) or diagnostic_count == 2:
            # Opt-in local test clients, all resources still registered to
            # this supervisor and protected by its single global lock.
            import authority_recovered_server_client as diagnostic_client
            count = diagnostic_count or 1
            results = []
            baseline = None
            def cancel_diagnostic():
                if stop[0]: raise InterruptedError('diagnostic cancelled')
            def verify_diagnostic():
                cancel_diagnostic()
                verify()
                cancel_diagnostic()
            for index in range(count):
                diagnostic = diagnostic_client.ServerClient(deadline, source_store.directory)
                diagnostics.append(diagnostic)
                diagnostic_out = out if count == 1 else out/('diagnostic-%02d' % (index+1))
                if count != 1: diagnostic_out.mkdir(mode=0o700)
                diagnostic_result = diagnostic_client.run_one(diagnostic, args=args, out=diagnostic_out, game=game,
                    home=home, uid=user.pw_uid, steam=steam, auth=auth, user=user.pw_name,
                    processes=processes, server_proc=proc, server_started=started, server_identity=identity,
                    checkpoint=checkpoint, recovery_target=target, server_expected=expected,
                    recovery_watch=watch, listener=listener, host=host, service=service, world=world,
                    session=session, control=control, check_server=verify_diagnostic, server_out=out,
                    expected_baseline=baseline, cancel_check=cancel_diagnostic)
                if count != 1:
                    baseline = diagnostic_client.settle_departure(host, world, control, diagnostic.server_tcp, deadline, verify_diagnostic,
                        diagnostic_result['client_ticket'], diagnostic_result['client_loaded_marker'])
                    diagnostic_result.update(departure_checkpoint_id=baseline.checkpoint_id,
                                             departure_checkpoint_sha256=baseline.sha256,
                                             departure_checkpoint_marker=baseline.marker)
                results.append(diagnostic_result)
            if count == 1: result['diagnostic_client'] = results[0]
            else: result['diagnostic_clients'] = results
        # Publish only after the private diagnostic socket has been accepted.
        # The endpoint contains a bearer secret; its directory is owner-only.
        fd = os.open(endpoint, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w', encoding='ascii') as stream:
            json.dump({'version':1,'control_host':'127.0.0.1','control_port':listener.getsockname()[1],
                       'file_host':'127.0.0.1','file_port':service.port,'file_token':service.token,'file_slot':1}, stream)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        result.update(serve(listener, host, deadline=deadline, check=check, should_stop=lambda: stop[0]))
        # Withdraw endpoint first, then disconnect peers; the coordinator's
        # last-disconnect path must pause and save before terminating X4.
        endpoint.unlink(); listener.close(); listener = None
        saved = settle_shutdown(control, world, store, check)
        control = None
        verify()
        result.update(success=True, final_world_state=world.session.state,
                      final_checkpoint_id=None if saved is None else saved.checkpoint_id,
                      final_checkpoint_sha256=None if saved is None else saved.sha256)
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = str(error) or type(error).__name__
    finally:
        errors=[]
        for number in handlers:
            try: signal.signal(number,signal.SIG_IGN)
            except BaseException as error: errors.append('cannot fence signals: '+type(error).__name__)
        try: endpoint.unlink(missing_ok=True)
        except BaseException as error: errors.append('endpoint cleanup: '+type(error).__name__)
        if listener is not None:
            try: listener.close()
            except BaseException as error: errors.append('listener cleanup: '+type(error).__name__)
        if control is not None and not (control._closed or control._failed):
            try: control.close()
            except BaseException as error: errors.append('control cleanup: '+type(error).__name__)
        for service in services:
            try: owned.close_owned_file_service(service)
            except BaseException as error: errors.append('service cleanup: '+type(error).__name__)
        if sock is not None:
            try: sock.close()
            except BaseException as error: errors.append('socket cleanup: '+type(error).__name__)
        if clock_sock is not None:
            try: clock_sock.close()
            except BaseException as error: errors.append('clock socket cleanup: '+type(error).__name__)
        helpers_stopped = cleanup_diagnostics(diagnostics, errors)
        remaining = stop_owned_processes(processes, helpers_stopped, errors)
        result['owned_processes_remaining']=remaining
        if remaining: errors.append('owned processes remain')
        if result['success'] and remaining == []:
            try:
                verify_final_recovery(watch)
                if (live.sha(target) != checkpoint.sha256 or
                        any(live.sha(path) != digest for path,digest in expected.items())):
                    raise ValueError('final protected recovery inputs changed')
            except BaseException as error:
                result.update(success=False, error='final recovery evidence invalid: '+str(error))
        if lockbox:
            lock_fd, lock_stat = lockbox[0]
            if remaining is None or remaining:
                errors.append('lock retained: owned process stop unconfirmed')
                try: os.close(lock_fd)
                except BaseException as error: errors.append('lock descriptor: '+type(error).__name__)
            else:
                try: live.release_lock_target(snapshot.LOCK_TARGET,lock_fd,lock_stat)
                except BaseException as error: errors.append('lock cleanup: '+type(error).__name__)
        try:
            if live.steam_identity(home,user.pw_uid) != steam: errors.append('Steam identity changed')
        except BaseException as error: errors.append('Steam identity unavailable: '+type(error).__name__)
        if remaining == []:
            for diagnostic in reversed(diagnostics):
                try: diagnostic.redact()
                except BaseException as error: errors.append('diagnostic lease cleanup: '+type(error).__name__)
        config=out/'case/extensions/x4_lan_lab/ui/config.lua'
        try:
            if config.is_file():
                text=config.read_text(encoding='ascii')
                redacted,count=re.subn(r'authority_control_lease="[0-9a-f]{32}"',
                    'authority_control_lease="redacted"',text)
                if count != 1: raise ValueError('invalid lease')
                config.write_text(redacted,encoding='ascii')
        except BaseException as error: errors.append('lease cleanup: '+type(error).__name__)
        if errors: result.update(success=False,cleanup_errors=errors)
        try: (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        finally:
            for number,handler in handlers.items():
                try: signal.signal(number,handler)
                except BaseException: pass
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True); parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--store',type=Path,default=source.DEFAULT_STORE)
    parser.add_argument('--display',required=True); parser.add_argument('--timeout',type=float,default=3600)
    parser.add_argument('--seed',type=int,default=276944566)
    diagnostic_options = parser.add_mutually_exclusive_group()
    diagnostic_options.add_argument('--diagnostic-client', action='store_true',
                        help='start one private Linux diagnostic client before serving other loopback clients')
    diagnostic_options.add_argument('--diagnostic-overlap', action='store_true',
                        help='start two overlapping private Linux diagnostic clients before serving other peers')
    diagnostic_options.add_argument('--diagnostic-clients', type=int, choices=(2,),
                        help='start two sequential private Linux diagnostic clients before serving other peers')
    try: result=run(parser.parse_args())
    except (OSError,ValueError,RuntimeError) as error: parser.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2)); return 0 if result['success'] else 1

if __name__ == '__main__': sys.exit(main())
