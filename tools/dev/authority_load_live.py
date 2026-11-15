#!/usr/bin/env python3
"""Opt-in isolated Linux X4 checkpoint load experiment; never runs on import.

The store and output must be beneath this checkout's .local. The chosen checkpoint
must be CURRENT. A fresh disposable profile is used; no Battle fixture is assumed.
"""
import argparse
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'tools/dev'))
from authority.checkpoints import CheckpointStore
from authority_control_cycle_evidence import read_cycle_evidence
from authority_cycle_live import ControlLogWatch as CycleLogWatch, MARKERS as CYCLE_MARKERS
from lockstep.launcher import extension
import linux_gate_live as live
import linux_snapshot_capture as snapshot


def local_directory(path):
    local = (REPO / '.local').resolve(strict=True)
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise ValueError('checkpoint store must be an existing non-symlink directory')
    resolved = path.resolve(strict=True)
    if resolved == local or not resolved.is_relative_to(local):
        raise ValueError('checkpoint store must be beneath .local')
    return resolved


def lua_literal(value):
    # Decimal byte escapes also handle whitespace, quotes and non-ASCII paths.
    return '"' + ''.join('\\%03d' % b for b in value.encode('utf-8')) + '"'


def install_probe(case, profile):
    lab = case / 'extensions/x4_lan_lab'
    if lab.is_symlink() or not lab.is_dir():
        raise ValueError('private extension missing')
    ui = lab / 'ui'
    shutil.copyfile(REPO/'tools/dev/authority_load_probe.lua', ui/'authority_load_probe.lua')
    (ui/'native_gate_snapshot.lua').unlink()
    (lab/'md/native_gate_battle.xml').unlink()
    (lab/'ui.xml').write_text(extension.ui_xml([*extension.BASE_UI, 'ui/authority_load_probe.lua']), encoding='utf-8')
    config = ui/'config.lua'
    config.chmod(0o600)
    config.write_text('X4LAN_CONFIG = {enabled=false, test_profile="45841", authority_load_probe=true, '
                      'authority_load_save_path='+lua_literal(str(profile/'save'))+'}\n', encoding='ascii')


def stage_checkpoint(store, checkpoint_id, profile):
    checkpoint = store.latest()  # verifies CURRENT, manifest, digest and entire gzip/XML
    if checkpoint.checkpoint_id != checkpoint_id:
        raise ValueError('requested checkpoint is not CURRENT')
    save_dir = profile / 'save'
    if any(save_dir.iterdir()):
        raise ValueError('new private save directory is not empty')
    target = save_dir / snapshot.SLOT
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    source_fd = os.open(checkpoint.path, flags)
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('checkpoint is not a regular file')
        dest_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(source_fd, 'rb') as source, os.fdopen(dest_fd, 'wb') as dest:
            source_fd = -1
            while True:
                part = source.read(1024*1024)
                if not part:
                    break
                size += len(part)
                if size > checkpoint.size:
                    raise ValueError('checkpoint grew during staging')
                digest.update(part)
                dest.write(part)
            after = os.fstat(source.fileno())
            if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                raise ValueError('checkpoint changed during staging')
            dest.flush();os.fsync(dest.fileno())
        if (digest.hexdigest(), size) != (checkpoint.sha256, checkpoint.size) or live.sha(target) != checkpoint.sha256:
            raise ValueError('staged checkpoint does not match sealed checkpoint')
    finally:
        if source_fd >= 0:
            os.close(source_fd)
    return checkpoint, target


def verify_origin(store_dir, checkpoint, profile):
    """Independently verify a completed single or two-cycle private source."""
    if store_dir.name == 'checkpoints':
        origin = store_dir.parent
        cycle_source = False
    elif store_dir.name == 'cycle-2' and store_dir.parent.name == 'checkpoints':
        origin = store_dir.parent.parent
        cycle_source = True
    else:
        raise ValueError('unsupported source checkpoint store path')
    result_path = origin/'result.json'
    if result_path.is_symlink() or not result_path.is_file() or result_path.stat().st_size > 65536:
        raise ValueError('source control result unavailable')
    result = json.loads(result_path.read_text(encoding='utf-8'))
    if (not isinstance(result, dict) or result.get('success') is not True or
        result.get('resume_confirmed') is not True or result.get('owned_processes_remaining') != []):
        raise ValueError('source control result does not identify a completed checkpoint')
    if cycle_source:
        saved_time = verify_cycle_origin(origin, store_dir, checkpoint, result)
    elif (result.get('native_save_event') is not True or result.get('file_verified') is not True or
          result.get('checkpoint_id') != checkpoint.checkpoint_id or
          result.get('sha256') != checkpoint.sha256 or result.get('size') != checkpoint.size):
        raise ValueError('source control result does not identify a completed checkpoint')
    else:
        evidence = read_cycle_evidence(CheckpointStore(store_dir), checkpoint.checkpoint_id,
                                       'X4 Authority isolated checkpoint')
        if (evidence.sha256, evidence.size) != (checkpoint.sha256, checkpoint.size):
            raise ValueError('source checkpoint evidence changed')
        saved_time = evidence.game_time
    original = origin/'case/home/.config/EgoSoft/X4/45841/content.xml'
    current = profile/'content.xml'
    if (original.is_symlink() or not original.is_file() or original.stat().st_size > 65536 or
        original.read_bytes() != current.read_bytes()):
        raise ValueError('source and destination extension lists differ')
    return saved_time


def verify_cycle_origin(origin, store_dir, checkpoint, result):
    rows = result.get('cycles')
    if (not isinstance(rows, list) or len(rows) != 2 or
        any(not isinstance(row, dict) for row in rows) or
        any(type(row.get('cycle')) is not int for row in rows) or
        [row.get('cycle') for row in rows] != [1, 2] or
        any(row.get('file_verified') is not True for row in rows)):
        raise ValueError('source cycle result is incomplete')
    config = origin/'case/extensions/x4_lan_lab/ui/config.lua'
    if config.is_symlink() or not config.is_file() or config.stat().st_size > 65536:
        raise ValueError('source cycle configuration unavailable')
    text = config.read_text(encoding='ascii')
    ids = re.findall(r'authority_cycle_id="([0-9a-f]{32})"', text)
    if len(ids) != 1 or text.count('authority_cycle_id') != 1:
        raise ValueError('source cycle identity unavailable')
    cycle_id = ids[0]
    first_dir = store_dir.parent/'cycle-1'
    if first_dir.is_symlink() or not first_dir.is_dir():
        raise ValueError('first cycle store unavailable')
    first_store = CheckpointStore(first_dir)
    second_store = CheckpointStore(store_dir)
    first = first_store.latest()
    second = second_store.latest()
    if second != checkpoint or first.checkpoint_id == second.checkpoint_id:
        raise ValueError('source cycle checkpoint mismatch')
    one = read_cycle_evidence(first_store, first.checkpoint_id, f'X4 Authority cycle 1 {cycle_id}')
    two = read_cycle_evidence(second_store, second.checkpoint_id, f'X4 Authority cycle 2 {cycle_id}',
                              previous_game_time=one.game_time)
    for row, evidence in zip(rows, (one, two)):
        if (row.get('checkpoint_id') != evidence.checkpoint_id or row.get('sha256') != evidence.sha256 or
            type(row.get('size')) is not int or row.get('size') != evidence.size or
            row.get('game_time') != str(evidence.game_time)):
            raise ValueError('source cycle evidence differs from checkpoint')
    log = origin/'case/home/.config/EgoSoft/X4/45841/engine-output.log'
    watch = CycleLogWatch(log)
    while True:
        previous = watch.offset
        if watch.poll(): break
        if watch.offset == previous: raise ValueError('incomplete source cycle log')
    if watch.counts != [1] * len(CYCLE_MARKERS):
        raise ValueError('source cycle log incomplete')
    return two.game_time


def verify_loaded_time(saved_time, ready_time):
    """Reject a clear regression; one millisecond covers observed XML rounding.

    This lower bound is empirical and does not prove the loaded save's identity.
    There is deliberately no upper bound on normal time spent entering the game.
    """
    if (not isinstance(saved_time, Decimal) or not saved_time.is_finite() or saved_time < 0 or
        type(ready_time) is not float or not math.isfinite(ready_time) or ready_time < 0):
        raise ValueError('invalid saved or loaded game time')
    if Decimal(str(ready_time)) + Decimal('0.001') < saved_time:
        raise ValueError('loaded game time precedes checkpoint time')


class LoadWatch:
    TAG = b'[X4LAN] AUTH_LOAD '
    MAX_LINE = 65536
    MAX_LOG = 256 << 20
    NUMBER = rb'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.identity = None
        self.carry = b''
        self.stage = 0
        self.ready_time = None
        self.advanced_time = None

    def poll(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError:
            return False
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size < self.offset or info.st_size > self.MAX_LOG:
                raise ValueError('load log changed or exceeded its size bound')
            identity = (info.st_dev, info.st_ino)
            if self.identity is not None and self.identity != identity:
                raise ValueError('load log was replaced')
            self.identity = identity
            os.lseek(fd, self.offset, os.SEEK_SET)
            for _ in range(4):
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                self.offset += len(chunk)
                lines = (self.carry + chunk).split(b'\n')
                self.carry = lines.pop()
                if len(self.carry) > self.MAX_LINE:
                    raise ValueError('load log line exceeded limit')
                for line in lines:
                    if len(line) > self.MAX_LINE:
                        raise ValueError('load log line exceeded limit')
                    if self.TAG not in line:
                        continue
                    row = line.split(self.TAG, 1)[1].strip()
                    if self.stage == 0 and row == b'ARMED':
                        self.stage = 1
                    elif self.stage == 1 and row == b'REQUEST':
                        self.stage = 2
                    elif self.stage in (2, 3):
                        name = b'READY' if self.stage == 2 else b'ADVANCED'
                        match = re.fullmatch(name + rb' time=(' + self.NUMBER + rb')', row)
                        if not match:
                            raise ValueError('invalid or out-of-order load receipt')
                        number = float(match.group(1))
                        if not math.isfinite(number) or number < 0:
                            raise ValueError('invalid load game time')
                        if self.stage == 2:
                            self.ready_time = number
                        else:
                            if number <= self.ready_time:
                                raise ValueError('game time did not advance')
                            self.advanced_time = number
                        self.stage += 1
                    else:
                        raise ValueError('duplicate, unexpected or failed load receipt')
            size = os.fstat(fd).st_size
            if size > self.MAX_LOG:
                raise ValueError('load log exceeded limit')
            return self.offset == size and not self.carry
        finally:
            os.close(fd)


def readonly_save_command(case, game, binds, lock, display, auth, username, seed, target):
    command = snapshot.command_for(case, game, binds, lock, display, auth, username, seed)
    index = command.index('--die-with-parent')
    command[index:index] = ['--ro-bind', str(target), str(target)]
    return command


def run(args):
    if sys.platform != 'linux' or os.geteuid() == 0:
        raise ValueError('run as the unprivileged Linux Steam desktop user')
    out = snapshot.output_path(args.out)
    store_dir = local_directory(args.store)
    store = CheckpointStore(store_dir)
    game = args.game.resolve(strict=True)
    if live.sha(game/'X4') != live.EXE_SHA or not (game/'extensions').is_dir() or not shutil.which('bwrap'):
        raise ValueError('pinned game or bubblewrap unavailable')
    if live.x4_executables():
        raise ValueError('another X4 process is running')
    if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?', args.display):
        raise ValueError('a local X11 display is required')
    auth = Path(os.environ.get('XAUTHORITY', ''))
    if not auth.is_file() or not os.access(auth, os.R_OK):
        raise ValueError('readable XAUTHORITY required')
    auth = auth.resolve(strict=True)
    if not math.isfinite(args.timeout) or args.timeout <= 0 or not 0 <= args.seed <= 0xffffffff:
        raise ValueError('invalid timeout or seed')
    import pwd
    user = pwd.getpwuid(os.geteuid());home = Path(user.pw_dir)
    steam = live.steam_identity(home, user.pw_uid)
    out.mkdir(mode=0o700, parents=True, exist_ok=False);out.chmod(0o700)
    result = {'success': False, 'scope': 'single isolated Linux X4 checkpoint load; no multiplayer',
              'steam_before': steam, 'read_only_staged_save': True}
    proc = started = lock_fd = lock_stat = None
    handlers = {}
    try:
        case, profile, binds, lock = snapshot.prepare_case(out, game, home)
        checkpoint, target = stage_checkpoint(store, args.checkpoint_id, profile)
        saved_time = verify_origin(store_dir, checkpoint, profile)
        install_probe(case, profile)
        lock_fd, lock_stat = live.create_lock_target(snapshot.LOCK_TARGET, user.pw_uid, user.pw_gid)
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            handlers[number] = signal.signal(number, snapshot.cancel_capture)
        if live.sha(target) != checkpoint.sha256:
            raise ValueError('staged checkpoint changed before launch')
        with (out/'process.log').open('wb') as log:
            command = readonly_save_command(case, game, binds, lock, args.display, auth, user.pw_name, args.seed, target)
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            started = live.start_ticks(proc.pid)
            deadline = time.monotonic() + args.timeout
            watch = LoadWatch(profile/'engine-output.log')
            while True:
                if time.monotonic() >= deadline: raise TimeoutError('load experiment timed out')
                if proc.poll() is not None: raise RuntimeError('owned X4 exited before load confirmation')
                if live.steam_identity(home, user.pw_uid) != steam: raise RuntimeError('Steam identity changed')
                caught_up = watch.poll()
                if caught_up and watch.stage == 4:
                    if live.sha(target) != checkpoint.sha256:
                        raise ValueError('staged checkpoint changed during load')
                    result.update(saved_game_time=str(saved_time), ready_game_time=watch.ready_time,
                                  advanced_game_time=watch.advanced_time)
                    verify_loaded_time(saved_time, watch.ready_time)
                    result.update(success=True, checkpoint_id=checkpoint.checkpoint_id, sha256=checkpoint.sha256,
                                  size=checkpoint.size, load_requested=True, game_ready=True,
                                  clock_not_before_saved=True)
                    break
                time.sleep(.1)
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = str(error)
    finally:
        if proc is not None and started is None and proc.poll() is None:
            try:
                proc.terminate();proc.wait(timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                result.update(success=False, cleanup_error='unidentified owned launcher cleanup failed')
        if started is not None:
            try:
                remaining = snapshot.stop_owned(proc, started)
                result['owned_processes_remaining'] = remaining
                if remaining: result.update(success=False, cleanup_error='owned process group remains')
            except (OSError, subprocess.TimeoutExpired):
                result.update(success=False, cleanup_error='owned process cleanup failed')
        if result['success']:
            try:
                while True:
                    previous = watch.offset
                    if watch.poll(): break
                    if watch.offset == previous: raise ValueError('incomplete final log line')
                if watch.stage != 4: raise ValueError('incomplete final load receipt')
            except (OSError, ValueError):
                result.update(success=False, error='final load receipt invalid')
        if lock_stat is not None:
            try: live.release_lock_target(snapshot.LOCK_TARGET, lock_fd, lock_stat)
            except (OSError, RuntimeError): result.update(success=False, cleanup_error='lock cleanup failed')
        for number, handler in handlers.items(): signal.signal(number, handler)
        try: result['steam_after'] = live.steam_identity(home, user.pw_uid)
        except (OSError, ValueError, RuntimeError): result['steam_after'] = None
        if result['steam_after'] != steam: result.update(success=False, error='Steam identity changed')
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--checkpoint-id', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--display', required=True)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--seed', type=int, default=276944566)
    args = parser.parse_args(argv)
    try: result = run(args)
    except (OSError, ValueError, RuntimeError) as error: parser.exit(1, 'REFUSED: '+str(error)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
