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
        server.install_probe(server_case, sock.getsockname()[1], lease, epoch)
        (out / 'checkpoints').mkdir(mode=0o700)
        store = CheckpointStore(out / 'checkpoints')
        lock_fd, lock_stat = live.create_lock_target(snapshot.LOCK_TARGET, user.pw_uid, user.pw_gid)
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            handlers[number] = signal.signal(number, snapshot.cancel_capture)
        deadline = time.monotonic() + args.timeout
        def spawn(command, log_path):
            with log_path.open('wb') as log:
                proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                        stderr=subprocess.STDOUT, start_new_session=True)
            # Record the child before any subsequent operation can raise.
            processes.append([proc, None])
            processes[-1][1] = live.start_ticks(proc.pid)
            return proc, processes[-1][1]
        server_proc, server_started = spawn(snapshot.command_for(server_case, game, server_binds,
            server_lock, args.display, auth, user.pw_name, args.seed), server_out / 'process.log')
        server_identity = None
        peer = None
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
            profile=server_profile, store=store, verify_checkpoint=read_cycle_evidence, timeout=min(130, args.timeout))
        service = joinfiles.FileService(secrets.token_hex(16), slots=(1,)).start()
        world = WorldCoordinator(epoch, adapter, store, SaveOffers(service, store), participants=experiment)
        handle = world.join('isolated-client')
        for operation in ('pause', 'save'):
            if time.monotonic() >= deadline: raise TimeoutError('server checkpoint timed out')
            if world.session.pending is None or world.session.pending.operation != operation:
                raise RuntimeError('unexpected coordinator operation')
            world.step()
            if client.game_identity(server_proc, server_started, game) != server_identity:
                raise RuntimeError('server X4 changed during checkpoint')
        ticket, target = offer_and_download(world, service, handle, out, client_profile)
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
        client_proc, client_started = spawn(command, client_out / 'process.log')
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
                    experiment.on_ready(world=world, handle=handle, ticket=ticket, target=target,
                        server_identity=server_identity, server_proc=server_proc, server_started=server_started,
                        client_identity=client_identity, client_proc=client_proc, client_started=client_started,
                        game=game, out=out, deadline=deadline, result=result)
                result['success'] = True
                break
            time.sleep(.1)
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = str(error)
    finally:
        if service is not None: service.close()
        if sock is not None: sock.close()
        for proc, started in reversed(processes):
            try:
                if started is not None:
                    remaining = snapshot.stop_owned(proc, started)
                    if remaining: result.update(success=False, cleanup_error='owned processes remain')
                elif proc.poll() is None:
                    proc.terminate(); proc.wait(timeout=15)
            except (OSError, subprocess.TimeoutExpired): result.update(success=False, cleanup_error='process cleanup failed')
        if result['success']:
            try:
                while True:
                    old = watch.offset
                    if watch.poll(): break
                    if old == watch.offset: raise ValueError('incomplete receipt')
                if (watch.stage != 2 or live.sha(target) != ticket['sha256'] or
                        any(live.sha(path) != digest for path, digest in expected.items())):
                    raise ValueError('final receipt invalid')
            except (OSError, ValueError): result.update(success=False, error='final receipt or staged state invalid')
        if lock_stat is not None:
            try: live.release_lock_target(snapshot.LOCK_TARGET, lock_fd, lock_stat)
            except (OSError, RuntimeError): result.update(success=False, cleanup_error='lock cleanup failed')
        for number, handler in handlers.items(): signal.signal(number, handler)
        try:
            if live.steam_identity(home, user.pw_uid) != steam: result.update(success=False, error='Steam identity changed')
        except (OSError, ValueError, RuntimeError): result.update(success=False, error='Steam identity unavailable')
        server_config = out/'server/case/extensions/x4_lan_lab/ui/config.lua'
        if server_config.is_file():
            try:
                text = server_config.read_text(encoding='ascii')
                redacted, count = re.subn(r'authority_control_lease="[0-9a-f]{32}"',
                                          'authority_control_lease="redacted"', text)
                if count != 1: raise ValueError('invalid lease')
                server_config.write_text(redacted, encoding='ascii')
            except (OSError, UnicodeError, ValueError): result.update(success=False, cleanup_error='lease cleanup failed')
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
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
