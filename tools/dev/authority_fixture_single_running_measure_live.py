#!/usr/bin/env python3
"""Opt-in CPU/RSS experiment on one disposable Linux X4 fixture instance.

The confirmed fixture is copied into a private profile and mounted read-only.
Importing this module does not start X4. A successful observation is not a
claim of identical rendering, FPS, cross-platform gameplay or exact load bytes.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import secrets
import select
import shutil
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.linux_proc_measurement import measure_running_window
from authority.linux_proc_sampler import LinuxProcSampler
import authority_fixture_checkpoint_source as fixture_source
import authority_recovery_live as recovery
import authority_saved_player_control_live as seat
import authority_saved_registry_checkpoint_source as fixture_checkpoint
import authority_tcp_job_client_live as socket_check
import linux_gate_live as live

SOURCE = ROOT / '.local/private-fixture-player-rejoin-scope-real-20261117-01/overlap-runner/server/checkpoints'
SOURCE_ID = 'checkpoint-9f85eb2743d543a5afa4321d7d16110b'
SOURCE_SHA = 'e236c26d9dd77003524e6d6ed0fff8bf5ce24ab469b9c5dfeb6799e790efc2c4'
MARKER = 'X4AuthorityPlayerFixtureMarker'


def install(case, profile, scripts, port, lease, original_install):
    if (set(scripts) != set(fixture_source.SAVED_SCRIPTS) or type(port) is not int or
            not 1 <= port <= 65535 or not re.fullmatch(r'[0-9a-f]{32}', lease)):
        raise ValueError('invalid private measurement installation')
    config = original_install(case, profile)
    lab = case / 'extensions/x4_lan_lab'
    ui, md = lab / 'ui', lab / 'md'
    for name, contents in scripts.items():
        (md / name).write_bytes(contents)
    names = ('authority_fixture_single_measure.lua', 'authority_fixture_single_measure_bootstrap.lua')
    for name in names:
        shutil.copyfile(ROOT / 'tools/dev' / name, ui / name)
    compiler = shutil.which('cc')
    if not compiler:
        raise ValueError('a C compiler is required for the private native UDP module')
    subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-shared', '-fPIC', str(ROOT / 'src/native/net.c'), '-ldl',
                    '-o', str(lab / 'native/x4lan_net.so')], check=True, capture_output=True)
    marker = ui / 'authority_checkpoint_marker_probe.lua'
    text = marker.read_text(encoding='utf-8')
    if text.count('X4AuthorityCheckpointMarker') != 5:
        raise ValueError('fixture marker probe changed')
    marker.write_text(text.replace('X4AuthorityCheckpointMarker', MARKER), encoding='utf-8')
    owner = ui / 'authority_recovery_probe.lua'
    owner.write_text(seat.replace_once(owner.read_text(encoding='utf-8'),
        " if state=='done' then return end\n",
        " if state=='done' then X4LAN_FIXTURE_SINGLE_MEASURE_UPDATE();return end\n"), encoding='utf-8')
    manifest = lab / 'ui.xml'
    hook = '    <file name="ui/authority_recovery_probe.lua" />\n'
    manifest.write_text(seat.replace_once(manifest.read_text(encoding='utf-8'), hook,
        ''.join('    <file name="ui/' + name + '" />\n' for name in names) + hook), encoding='utf-8')
    text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'):
        raise ValueError('unexpected recovery configuration')
    config.write_text(text[:-2] + ',authority_single_measure=true,'
        f'authority_single_measure_port={port},authority_single_measure_lease="{lease}"' + '}\n', encoding='ascii')
    return config, [*(md / name for name in scripts), *(ui / name for name in names),
                    lab / 'native/x4lan_net.so']


class FixtureClock:
    """Nonce-correlated local clock bound to an owned X4 socket and process."""
    def __init__(self, sock, lease, identity, game, guard, deadline):
        self.sock, self.lease, self.guard, self.deadline = sock, lease, guard, deadline
        self.peer = None
        image = (game / 'X4').stat()
        self.process = {'pid': identity[0], 'start_ticks': identity[1],
                        'exe_dev': image.st_dev, 'exe_ino': image.st_ino}

    def _read(self, expected, nonce=None):
        while True:
            self.guard()
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('fixture clock deadline expired')
            if not select.select([self.sock], [], [], min(.1, remaining))[0]:
                continue
            raw, peer = self.sock.recvfrom(769)
            if len(raw) > 768 or peer[0] != '127.0.0.1':
                raise ValueError('unexpected clock sender')
            if self.peer is not None and self.peer != peer:
                raise ValueError('fixture clock peer changed')
            if not socket_check.socket_owner(peer, self.sock.getsockname(), self.process):
                raise ValueError('fixture clock socket owner differs')
            fields = raw.decode('ascii').split('|')
            if expected == 'READY':
                if fields != ['READY', self.lease]:
                    raise ValueError('unexpected fixture clock ready')
                self.peer = peer
                self.guard()
                return None
            if len(fields) != 4 or fields[:3] != [expected, self.lease, nonce]:
                raise ValueError('unexpected fixture clock receipt')
            value = float(fields[3])
            if not math.isfinite(value) or value < 0:
                raise ValueError('invalid fixture clock value')
            self.guard()
            return value

    def _request(self, name, expected):
        if self.peer is None:
            raise ValueError('fixture clock is not ready')
        self.guard()
        if not socket_check.socket_owner(self.peer, self.sock.getsockname(), self.process):
            raise ValueError('fixture clock socket owner changed')
        nonce = secrets.token_hex(16)
        data = f'{name}|{self.lease}|{nonce}'.encode('ascii')
        if time.monotonic() >= self.deadline or self.sock.sendto(data, self.peer) != len(data):
            raise RuntimeError('fixture clock request failed')
        return self._read(expected, nonce)

    def resume(self):
        self._read('READY')
        return self._request('RESUME', 'RESUMED')

    def sample(self):
        return self._request('CLOCK', 'CLOCK_RESULT')


def run(args):
    if (type(args.duration) not in (int, float) or not math.isfinite(args.duration) or
            not 60 <= args.duration <= 120 or type(args.timeout) not in (int, float) or
            not math.isfinite(args.timeout) or args.timeout < args.duration + 120):
        raise ValueError('measurement requires 60 to 120 seconds and sufficient recovery time')
    if Path(args.store).resolve(strict=True) != SOURCE.resolve(strict=True):
        raise ValueError('only the pinned fixture checkpoint is permitted')
    out = recovery.snapshot.output_path(args.out)
    if out.resolve().is_relative_to(SOURCE.parent.resolve(strict=True)):
        raise ValueError('output must be outside the source directory')
    lease = secrets.token_hex(16)
    old = (recovery.stage_confirmed_recovery, recovery.verify_source, recovery.install_probe,
           recovery.extra_protected_files, recovery.observation_callback, recovery.result_finalizer,
           recovery.base.readonly_save_command)
    scripts = checkpoint = profile_path = extra = None
    measurement = [None]
    def stage(store, profile):
        return old[0](store, profile, marker_script=MARKER)
    def verify(store, selected, profile):
        nonlocal scripts, checkpoint, profile_path
        if selected.checkpoint_id != SOURCE_ID or selected.sha256 != SOURCE_SHA:
            raise ValueError('fixture source does not match pinned checkpoint')
        scripts = fixture_checkpoint.verify_recovered(store, selected, profile)
        checkpoint, profile_path = selected, profile
    def install_private(case, profile):
        nonlocal extra
        if scripts is None:
            raise ValueError('fixture source not verified')
        config, extra = install(case, profile, scripts, sock.getsockname()[1], lease, old[2])
        return config
    def protected(_case, _profile):
        if extra is None:
            raise ValueError('measurement files not installed')
        return extra
    def readonly(*values):
        target = values[-1]
        if target.name != 'save_008.xml.gz' or target.parent.name != 'save':
            raise ValueError('unexpected isolated save path')
        command = old[6](*values)
        pos = command.index('--die-with-parent')
        command[pos:pos] = ['--ro-bind', str(target.parent), str(target.parent)]
        return command
    def observe(*, game, identity, deadline, guard, **_kwargs):
        if (type(identity) is not tuple or len(identity) != 2 or
                any(type(value) is not int or value <= 0 for value in identity)):
            raise ValueError('owned X4 identity unavailable')
        clock = FixtureClock(sock, lease, identity, game, guard, deadline)
        resume_time = clock.resume()
        supervisor = (os.getpid(), live.start_ticks(os.getpid()))
        sampler = LinuxProcSampler({'single_x4': identity, 'supervisor': supervisor})
        checks = [0]
        def check():
            checks[0] += 1
            guard()
        result = measure_running_window(enabled=True, sampler=sampler,
            read_running_game_time=clock.sample, tick=lambda: time.sleep(.1), check=check,
            duration_seconds=args.duration, deadline=deadline)
        if result['game_time_before'] < resume_time or len(result['samples']) < 4:
            raise ValueError('measurement clock or sample count differs')
        result.update(resume_game_time=resume_time, owner_context_checks=checks[0],
                      supervisor_cpu_included_in_separate_process=True,
                      supervisor_scope='Python recovery runner only; Cage, Xwayland and scope launcher excluded',
                      diagnostic_overhead_included=True,
                      small_protected_files_hashed_during_measurement=True,
                      staged_save_hashed_before_and_after_measurement=True,
                      staged_save_hashed_during_measurement=False,
                      running_game_clock_checked_at_endpoints=True)
        measurement[0] = result
        return {'single_process_measurement': result}
    def final(result):
        if result.get('success') is not True:
            return
        if (measurement[0] is None or checkpoint is None or result.get('owned_processes_remaining') != [] or
                fixture_checkpoint.verify_recovered(args.store, checkpoint, profile_path) != scripts):
            raise ValueError('source or process cleanup not confirmed')
        result.update(scope='one running disposable Linux X4 from pinned fixture checkpoint',
                      no_save_requested=True, save_directory_read_only=True,
                      same_rendered_scene_as_multiplayer_proven=False, fps_measured=False,
                      gameplay_proven=False, windows_tested=False)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
        try:
            (recovery.stage_confirmed_recovery, recovery.verify_source, recovery.install_probe,
             recovery.extra_protected_files, recovery.observation_callback, recovery.result_finalizer,
             recovery.base.readonly_save_command) = (stage, verify, install_private, protected, observe, final, readonly)
            return recovery.run(SimpleNamespace(game=args.game, store=args.store, out=args.out,
                                                display=args.display, timeout=args.timeout, seed=args.seed))
        finally:
            (recovery.stage_confirmed_recovery, recovery.verify_source, recovery.install_probe,
             recovery.extra_protected_files, recovery.observation_callback, recovery.result_finalizer,
             recovery.base.readonly_save_command) = old


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--display', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--store', type=Path, default=SOURCE)
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--seed', type=int, default=276944566)
    try:
        result = run(parser.parse_args())
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result.get('success') is True else 1


if __name__ == '__main__':
    sys.exit(main())
