#!/usr/bin/env python3
"""Disposable Linux server-to-client checkpoint experiment (no admission/gameplay).

Two independently isolated X4 processes run under a single supervisor. A real
server bridge produces a checkpoint, then the coordinator offers it over local
TCP for a fresh client to request loading. Client load receipts are observations,
not proof of the exact file X4 read. The coordinator stays paused and never
marks the client ready. This tool does not start X4 on import.
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
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_download_load_live as client
import authority_load_live as load
import authority_world_bridge_live as server
import linux_gate_live as live
import linux_snapshot_capture as snapshot
from authority.checkpoints import CheckpointStore
from authority.local_control_bridge import LocalControlBridge
from authority.save_transfer import SaveOffers, receive
from authority.world import WorldCoordinator
from authority_control_cycle_evidence import read_cycle_evidence
from lockstep.launcher import joinfiles


def offer_and_download(world, service, handle, out, profile):
    """Transfer the coordinator's *current* offer without admitting the client."""
    if any((profile / 'save').iterdir()):
        raise ValueError('private client save directory is not empty')
    offer = world.offer_load(handle)
    ticket = dict(world_epoch=offer.world_epoch, connection_handle=offer.connection_handle,
                  baseline_id=offer.baseline_id, load_generation=offer.load_generation,
                  checkpoint_id=offer.save.checkpoint_id, sha256=offer.save.sha256,
                  attempt_id=secrets.token_hex(16), slot='save_009')
    download = receive('127.0.0.1', service.port, service.token, 1, offer.save,
                       out / 'download', retries=0, timeout=60)
    target = profile / 'save' / snapshot.SLOT
    if target.exists() or target.is_symlink():
        raise ValueError('client save target appeared during transfer')
    download.rename(target)
    target.chmod(0o400)
    if target.stat().st_size != offer.save.size or live.sha(target) != offer.save.sha256:
        raise ValueError('client staged checkpoint differs from offer')
    return ticket, target


def observe_open_save(pid, target):
    """Sample matching regular descriptors; offsets do not prove a complete read.

    An empty list means no matching descriptor was observed in this sample, not
    that the file was never opened. Inaccessible process descriptors are skipped.
    """
    expected = target.stat()
    if not stat.S_ISREG(expected.st_mode):
        raise ValueError('staged save is not regular')
    results = []
    for path in (Path('/proc') / str(pid) / 'fd').iterdir():
        if not path.name.isdecimal():
            continue
        try:
            candidate = path.stat()
            if (not stat.S_ISREG(candidate.st_mode) or
                    (candidate.st_dev, candidate.st_ino) != (expected.st_dev, expected.st_ino)):
                continue
            fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
            try:
                actual = os.fstat(fd)
                if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                    continue
                lines = (path.parent.parent / 'fdinfo' / path.name).read_text().splitlines()
                positions = [int(line.split(':', 1)[1].strip()) for line in lines if line.startswith('pos:')]
                if len(positions) == 1 and positions[0] >= 0:
                    results.append(positions[0])
            finally:
                os.close(fd)
        except (OSError, ValueError):
            continue
    return results


def spawn_owned_gated(command, log_path, processes):
    """Capture the child and its start identity before releasing the launcher.

    This must run in the main thread. A signal in the small interval between
    the final check and the gate write can still permit a brief launch; the
    deferred signal then aborts the run and invokes owned-process cleanup.
    """
    deferred = [None]
    previous = {}
    read_fd = write_fd = None
    def remember(number, _frame):
        deferred[0] = deferred[0] or number
    try:
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            previous[number] = signal.signal(number, remember)
        read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
        with log_path.open('wb') as log:
            proc = subprocess.Popen([sys.executable, str(ROOT/'tools/dev/authority_exec_gate.py'),
                                     str(read_fd), *command], stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True, pass_fds=(read_fd,))
            processes.append([proc, None])
        os.close(read_fd); read_fd = None
        started = live.start_ticks(proc.pid)
        if type(started) is not int or started < 0:
            raise RuntimeError('owned launcher start identity unavailable')
        processes[-1][1] = started
        if proc.poll() is not None or live.start_ticks(proc.pid) != started:
            raise RuntimeError('owned launch gate changed')
        if deferred[0] is not None:
            raise InterruptedError('signal ' + str(deferred[0]))
        if os.write(write_fd, b'G') != 1:
            raise RuntimeError('launch gate refused')
        os.close(write_fd); write_fd = None
        if deferred[0] is not None:
            raise InterruptedError('signal ' + str(deferred[0]))
    finally:
        for fd in (read_fd, write_fd):
            if fd is not None:
                try: os.close(fd)
                except OSError: pass
        for number, handler in previous.items():
            signal.signal(number, handler)
    # A signal may have arrived after the last gate check while handlers were
    # still deferred; inspect it after the original handlers are restored.
    if deferred[0] is not None:
        raise InterruptedError('signal ' + str(deferred[0]))
    return proc, started


def start_owned_file_service(token, services):
    """Register the bound service before starting its thread or raising signals."""
    deferred = [None]
    previous = {}
    def remember(number, _frame):
        deferred[0] = deferred[0] or number
    try:
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            previous[number] = signal.signal(number, remember)
        service = joinfiles.FileService(token, slots=(1,))
        try:
            services.append(service)
        except BaseException:
            service.server.server_close()
            raise
        if deferred[0] is not None:
            raise InterruptedError('signal ' + str(deferred[0]))
        service.start()
        if deferred[0] is not None:
            raise InterruptedError('signal ' + str(deferred[0]))
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    if deferred[0] is not None:
        raise InterruptedError('signal ' + str(deferred[0]))
    return service


def close_owned_file_service(service):
    """Avoid shutdown() before serve_forever has actually started."""
    thread = service.thread
    try:
        if thread is not None and thread.is_alive():
            service.close()
            thread.join(timeout=2)
            if thread.is_alive():
                raise RuntimeError('file service thread remains')
        else:
            service.server.server_close()
    except BaseException:
        # Even if shutdown failed, attempt to release the owned listener.
        try: service.server.server_close()
        except BaseException: pass
        raise


def check_live_context(*, deadline, server_proc, server_started, server_identity,
                       client_proc, client_started, client_identity, game, home,
                       uid, steam, target, ticket, expected):
    """Point-in-time process/Steam and protected-byte checks for opt-in hooks."""
    def check_identities():
        if (time.monotonic() >= deadline or
            client.game_identity(server_proc, server_started, game) != server_identity or
            client.game_identity(client_proc, client_started, game) != client_identity or
            live.steam_identity(home, uid) != steam):
            raise RuntimeError('deadline, process or Steam identity changed')
    check_identities()
    if (live.sha(target) != ticket['sha256'] or
            any(live.sha(path) != digest for path, digest in expected.items())):
        raise ValueError('client staged save or protected configuration changed')
    check_identities()
    return True


def check_final_recovery_files(result, experiment):
    """Recheck protected recovery inputs after owned cleanup, before redaction."""
    if not result.get('success'): return
    check = getattr(experiment, 'check_server_files', None)
    if check is None: return
    try:
        if not callable(check) or check() is not True: raise ValueError('recovery protection failed')
    except BaseException as error:
        result.update(success=False, error='final recovery state invalid: '+(str(error) or type(error).__name__))


def run(args, *, experiment=None):
    if sys.platform != 'linux' or os.geteuid() == 0:
        raise ValueError('unprivileged Linux desktop user required')
    out = snapshot.output_path(args.out)
    game = args.game.resolve(strict=True)
    if live.sha(game / 'X4') != live.EXE_SHA or not (game / 'extensions').is_dir() or not shutil.which('bwrap'):
        raise ValueError('pinned X4 or bubblewrap unavailable')
    if live.x4_executables():
        raise ValueError('another X4 process is running')
    if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?', args.display):
        raise ValueError('local X11 display required')
    auth = Path(os.environ.get('XAUTHORITY', ''))
    if not auth.is_file() or not os.access(auth, os.R_OK):
        raise ValueError('readable XAUTHORITY required')
    auth = auth.resolve(strict=True)
    if not math.isfinite(args.timeout) or args.timeout <= 0 or not 0 <= args.seed <= 0xffffffff:
        raise ValueError('invalid timeout or seed')
    user = pwd.getpwuid(os.geteuid())
    home = Path(user.pw_dir)
    steam = live.steam_identity(home, user.pw_uid)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = {'success': False, 'scope': 'two isolated Linux X4 processes; localhost transfer; no admission or gameplay'}
    processes = []
    services = []
    sock = service = lock_fd = lock_stat = None
    handlers = {}
    config = target = watch = ticket = protected = None
    try:
        server_out, client_out = out / 'server', out / 'client'
        server_out.mkdir(mode=0o700); client_out.mkdir(mode=0o700)
        server_case, server_profile, server_binds, server_lock = snapshot.prepare_case(server_out, game, home)
        client_case, client_profile, client_binds, client_lock = snapshot.prepare_case(client_out, game, home)
        if any((server_profile / 'save').iterdir()) or any((client_profile / 'save').iterdir()):
            raise ValueError('isolated profiles are not empty')
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('127.0.0.1', 0)); sock.settimeout(.25)
        lease, epoch = secrets.token_hex(16), secrets.token_hex(16)
        marker_required = getattr(experiment, 'marker_required', False) is True
        recovery_install = getattr(experiment, 'install_recovery_server', None)
        if recovery_install is not None:
            if not callable(recovery_install) or not marker_required:
                raise ValueError('invalid recovery installation hook')
            recovery_install(server_case, server_profile, sock.getsockname()[1], lease, epoch)
        elif marker_required:
            server.install_probe(server_case, sock.getsockname()[1], lease, epoch, marker_required=True)
        else:
            server.install_probe(server_case, sock.getsockname()[1], lease, epoch)
        (out / 'checkpoints').mkdir(mode=0o700)
        store = CheckpointStore(out / 'checkpoints')
        lock_fd, lock_stat = live.create_lock_target(snapshot.LOCK_TARGET, user.pw_uid, user.pw_gid)
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            handlers[number] = signal.signal(number, snapshot.cancel_capture)
        deadline = time.monotonic() + args.timeout
        recovery_command = getattr(experiment, 'recovery_server_command', None)
        if recovery_command is not None:
            if not callable(recovery_command): raise ValueError('invalid recovery command hook')
            command = recovery_command(server_case, game, server_binds, server_lock,
                args.display, auth, user.pw_name, args.seed)
        else:
            command = snapshot.command_for(server_case, game, server_binds,
                server_lock, args.display, auth, user.pw_name, args.seed)
        server_proc, server_started = spawn_owned_gated(command, server_out / 'process.log', processes)
        server_identity = None
        peer = None
        recovered_enroll = getattr(experiment, 'enroll_recovered_server', None)
        if recovered_enroll is not None:
            if not callable(recovered_enroll): raise ValueError('invalid recovery enrollment hook')
            peer, server_identity = recovered_enroll(sock=sock, lease=lease, epoch=epoch, deadline=deadline,
                server_proc=server_proc, server_started=server_started, game=game,
                steam=steam, home=home, uid=user.pw_uid, profile=server_profile)
            if (not isinstance(peer,tuple) or len(peer)!=2 or peer[0]!='127.0.0.1' or
                    type(peer[1]) is not int or not 1<=peer[1]<=65535 or server_identity is None or
                    time.monotonic()>=deadline or client.game_identity(server_proc,server_started,game)!=server_identity or
                    live.steam_identity(home,user.pw_uid)!=steam):
                raise RuntimeError('recovered server enrollment was not confirmed')
        while peer is None:
            if time.monotonic() >= deadline: raise TimeoutError('server enrollment timed out')
            identity = client.game_identity(server_proc, server_started, game)
            if identity is not None:
                if server_identity is not None and identity != server_identity: raise RuntimeError('server X4 changed')
                server_identity = identity
            elif server_identity is not None: raise RuntimeError('server X4 disappeared')
            if live.steam_identity(home, user.pw_uid) != steam: raise RuntimeError('Steam identity changed')
            try: data, address = sock.recvfrom(769)
            except socket.timeout: continue
            if data == f'HELLO|{lease}|{epoch}'.encode('ascii') and address[0] == '127.0.0.1':
                if server_identity is None: raise RuntimeError('server enrollment without owned X4')
                peer = address
        adapter = LocalControlBridge(enabled=True, sock=sock, peer=peer, lease=lease, world_epoch=epoch,
            profile=server_profile, store=store, verify_checkpoint=read_cycle_evidence, timeout=min(130, args.timeout),
            marker_required=marker_required)
        service = start_owned_file_service(secrets.token_hex(16), services)
        world = WorldCoordinator(epoch, adapter, store, SaveOffers(service, store), participants=experiment)
        join = getattr(experiment, 'join', None)
        handle = join(world) if callable(join) else world.join('isolated-client')
        recovery_files = getattr(experiment, 'check_server_files', None)
        if recovery_files is not None and not callable(recovery_files):
            raise ValueError('invalid recovery protection hook')
        for operation in ('pause', 'save'):
            if time.monotonic() >= deadline: raise TimeoutError('server checkpoint timed out')
            if recovery_files is not None and recovery_files() is not True:
                raise ValueError('recovery server protection failed')
            if world.session.pending is None or world.session.pending.operation != operation:
                raise RuntimeError('unexpected coordinator operation')
            world.step()
            if client.game_identity(server_proc, server_started, game) != server_identity:
                raise RuntimeError('server X4 changed during checkpoint')
            if recovery_files is not None and recovery_files() is not True:
                raise ValueError('recovery server protection failed')
        transfer = getattr(experiment, 'offer_and_download', None)
        ticket, target = (transfer(world, service, handle, out, client_profile) if callable(transfer)
                          else offer_and_download(world, service, handle, out, client_profile))
        if time.monotonic() >= deadline: raise TimeoutError('transfer timed out')
        config = client.install_probe(client_case, client_profile, ticket)
        protected = [config, client_case/'extensions/x4_lan_lab/ui.xml', client_profile/'content.xml',
                     client_profile/'config.xml']
        protected += [client_case/'extensions/x4_lan_lab/ui'/name for name in
                      ('client_load_barrier.lua', 'x4_client_load_engine.lua', 'authority_download_load_probe.lua')]
        if experiment is not None:
            protected += experiment.protected(client_case)
        expected = {path: live.sha(path) for path in protected}
        command = load.readonly_save_command(client_case, game, client_binds, client_lock,
                    args.display, auth, user.pw_name, args.seed, target)
        pos = command.index('--die-with-parent')
        for path in protected:
            command[pos:pos] = ['--ro-bind', str(path), str(path)]; pos += 3
        client_proc, client_started = spawn_owned_gated(command, client_out / 'process.log', processes)
        watch = client.ReceiptWatch(client_profile/'engine-output.log', ticket)
        client_identity = None
        save_fd_offsets = []
        while True:
            if time.monotonic() >= deadline: raise TimeoutError('client load observation timed out')
            if client.game_identity(server_proc, server_started, game) != server_identity:
                raise RuntimeError('server X4 disappeared or changed')
            identity = client.game_identity(client_proc, client_started, game)
            if identity is not None:
                if client_identity is not None and identity != client_identity: raise RuntimeError('client X4 changed')
                client_identity = identity
            elif client_identity is not None: raise RuntimeError('client X4 disappeared')
            if identity is not None:
                save_fd_offsets.extend(observe_open_save(identity[0], target))
            if live.steam_identity(home, user.pw_uid) != steam: raise RuntimeError('Steam identity changed')
            if any(live.sha(path) != digest for path, digest in expected.items()):
                raise ValueError('client protected configuration changed')
            pump_loading = getattr(experiment, 'pump_loading', None)
            if pump_loading is not None:
                if not callable(pump_loading): raise ValueError('invalid load pump hook')
                pump_loading()
            caught_up = watch.poll()
            if watch.stage and client_identity is None: raise RuntimeError('receipt without owned X4')
            if caught_up and watch.stage == 2:
                if world.session.state != 'paused' or world.session.ready_players:
                    raise RuntimeError('unexpected server state or admission')
                if live.sha(target) != ticket['sha256']: raise ValueError('staged checkpoint changed')
                result.update(server_checkpoint_verified=True, transfer_verified=True,
                    client_load_requested=True, client_pause_observed=True, server_state='paused',
                    client_save_fd_observed=bool(save_fd_offsets),
                    client_save_fd_max_offset=max(save_fd_offsets) if save_fd_offsets else None,
                    exact_loaded_file_proven=False, client_admitted=False, gameplay_tested=False)
                if experiment is not None:
                    extra = {'steam_identity': steam} if getattr(experiment, 'requires_steam_identity', False) else {}
                    if getattr(experiment, 'requires_verification_context', False) is True:
                        def check_protected():
                            return check_live_context(deadline=deadline, server_proc=server_proc,
                                server_started=server_started, server_identity=server_identity,
                                client_proc=client_proc, client_started=client_started,
                                client_identity=client_identity, game=game, home=home,
                                uid=user.pw_uid, steam=steam, target=target, ticket=ticket, expected=expected)
                        extra['check_protected'] = check_protected
                    experiment.on_ready(world=world, handle=handle, ticket=ticket, target=target,
                        server_identity=server_identity, server_proc=server_proc, server_started=server_started,
                        client_identity=client_identity, client_proc=client_proc, client_started=client_started,
                        game=game, out=out, deadline=deadline, result=result, **extra)
                result['success'] = True
                break
            time.sleep(.1)
    except BaseException as error:
        result.update(success=False, error=str(error) or type(error).__name__)
        if not isinstance(error, (Exception, KeyboardInterrupt)):
            raise
    finally:
        cleanup_errors = []
        all_stopped = True
        remaining_owned = []
        def cleanup_error(message, error=None):
            cleanup_errors.append(message + ((': ' + type(error).__name__) if error is not None else ''))
            result['success'] = False
        # A repeated signal must not strand one of the owned resources.
        for number in handlers:
            try: signal.signal(number, signal.SIG_IGN)
            except BaseException as error: cleanup_error('cannot fence cleanup signals', error)
        helper_stopped = True
        try:
            hook = getattr(experiment, 'cleanup_before_owned_processes', None)
            if hook is not None and (not callable(hook) or hook() is not True):
                raise RuntimeError('helper stop unconfirmed')
        except BaseException as error:
            helper_stopped = False
            all_stopped = False
            cleanup_error('helper cleanup unconfirmed', error)
        for owned_service in reversed(services):
            try: close_owned_file_service(owned_service)
            except BaseException as error: cleanup_error('service cleanup failed', error)
        if sock is not None:
            try: sock.close()
            except BaseException as error: cleanup_error('socket cleanup failed', error)
        for proc, started in reversed(processes) if helper_stopped else ():
            try:
                if started is not None:
                    remaining = snapshot.stop_owned(proc, started)
                    if not isinstance(remaining, list) or any(type(pid) is not int or pid <= 0 for pid in remaining):
                        raise RuntimeError('invalid owned cleanup result')
                    remaining_owned.extend(remaining)
                    if remaining:
                        all_stopped = False
                        cleanup_error('owned processes remain')
                else:
                    # An unrecorded start identity cannot have passed the exec gate.
                    if proc.poll() is None:
                        proc.terminate(); proc.wait(timeout=15)
                    cleanup_error('owned launcher start identity unavailable')
            except BaseException as error:
                all_stopped = False
                cleanup_error('process cleanup failed', error)
        result['owned_processes_remaining'] = remaining_owned if helper_stopped else None
        result['owned_cleanup_confirmed'] = all_stopped
        if result['success']:
            try:
                while True:
                    old = watch.offset
                    if watch.poll(): break
                    if old == watch.offset: raise ValueError('incomplete receipt')
                if (watch.stage != 2 or live.sha(target) != ticket['sha256'] or
                        any(live.sha(path) != digest for path, digest in expected.items())):
                    raise ValueError('final receipt invalid')
            except BaseException as error:
                result.update(success=False, error='final receipt or staged state invalid: ' +
                              (str(error) or type(error).__name__))
        if lock_stat is not None:
            if all_stopped:
                try: live.release_lock_target(snapshot.LOCK_TARGET, lock_fd, lock_stat)
                except BaseException as error: cleanup_error('lock cleanup failed', error)
            else:
                cleanup_error('lock retained: owned process stop unconfirmed')
                try: os.close(lock_fd)
                except BaseException as error: cleanup_error('lock descriptor close failed', error)
        try:
            if live.steam_identity(home, user.pw_uid) != steam:
                cleanup_error('Steam identity changed')
        except BaseException as error: cleanup_error('Steam identity unavailable', error)
        check_final_recovery_files(result, experiment)
        server_config = out/'server/case/extensions/x4_lan_lab/ui/config.lua'
        try:
            if server_config.is_file():
                text = server_config.read_text(encoding='ascii')
                redacted, count = re.subn(r'authority_control_lease="[0-9a-f]{32}"',
                                          'authority_control_lease="redacted"', text)
                if count != 1: raise ValueError('invalid lease')
                server_config.write_text(redacted, encoding='ascii')
        except BaseException as error: cleanup_error('lease cleanup failed', error)
        if cleanup_errors: result['cleanup_error'] = '; '.join(cleanup_errors)
        try:
            (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        finally:
            for number, handler in handlers.items():
                try: signal.signal(number, handler)
                except BaseException: pass
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game', required=True, type=Path); p.add_argument('--out', required=True, type=Path)
    p.add_argument('--display', required=True); p.add_argument('--timeout', type=float, default=600)
    p.add_argument('--seed', type=int, default=276944566)
    try: result = run(p.parse_args())
    except (OSError, ValueError, RuntimeError) as error: p.exit(1, 'REFUSED: '+str(error)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1

if __name__ == '__main__': sys.exit(main())
