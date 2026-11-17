#!/usr/bin/env python3
"""Save and verify registered fixture ships in one disposable Linux X4 run.

This opt-in diagnostic starts a private game through the existing recovery
runner. It does not admit clients or establish multiplayer or flight.
"""
import argparse
import json
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.checkpoints import CheckpointStore
from authority_control_cycle_evidence import read_cycle_evidence
from authority_player_registry_checkpoint_bridge import PlayerRegistryCheckpointBridge
from authority_tcp_job_client_live import socket_owner
import authority_saved_fixture_log as fixture_log
import authority_saved_player_registry_live as registry

seat = registry.seat
recovery = seat.recovery


def install_save_bridge(case, profile, scripts, *, port, lease, world_epoch,
                        registry_installer, **kwargs):
    """Add a private save bridge after the existing registry and seat probes."""
    config, protected = registry_installer(case, profile, scripts, **kwargs)
    lab = case / 'extensions/x4_lan_lab'
    ui = lab / 'ui'
    additions = []
    for source, name in (
        (ROOT / 'src/authority/lua/control_state.lua', 'authority_control_state.lua'),
        (ROOT / 'src/authority/lua/x4_control_engine.lua', 'x4_control_engine.lua'),
        (ROOT / 'src/authority/lua/local_control_bridge.lua', 'local_control_bridge.lua'),
        (ROOT / 'tools/dev/authority_world_bridge_probe.lua', 'authority_world_bridge_probe.lua'),
    ):
        target = ui / name
        if target.exists() or target.is_symlink():
            raise ValueError('private save bridge file already exists')
        shutil.copyfile(source, target)
        additions.append(target)
    compiler = shutil.which('cc')
    if compiler is None:
        raise ValueError('C compiler required for private UDP module')
    native = lab / 'native/x4lan_net.so'
    if native.exists() or native.is_symlink():
        raise ValueError('private native module already exists')
    subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-shared', '-fPIC', str(ROOT / 'src/native/net.c'), '-ldl', '-o', str(native)],
                   check=True, capture_output=True)
    control_owner = ui / 'authority_player_control_live_owner.lua'
    control_owner.write_text(seat.replace_once(control_owner.read_text(encoding='utf-8'),
        'assert(t-start<o.timeout)',
        "assert((type(X4LAN_REGISTRY_SAVE_READY)=='function' and X4LAN_REGISTRY_SAVE_READY()) or t-start<o.timeout)"),
        encoding='utf-8')
    marker_probe = ui / 'authority_checkpoint_marker_probe.lua'
    marker_probe.write_text(seat.replace_once(marker_probe.read_text(encoding='utf-8'),
        "RegisterEvent('X4AuthorityPlayerFixtureMarker.Stored',function(_,marker)\n",
        "RegisterEvent('X4AuthorityPlayerFixtureMarker.Stored',function(_,marker)\n"
        " if phase=='load' and state=='done' then return end\n"), encoding='utf-8')
    owner = ui / 'authority_saved_player_control_owner.lua'
    owner.write_text(owner.read_text(encoding='utf-8') +
                     '\nfunction X4LAN_REGISTRY_SAVE_READY() return fenced end\n', encoding='utf-8')
    dispatcher = ui / 'authority_saved_player_registry_dispatch.lua'
    text = seat.replace_once(dispatcher.read_text(encoding='utf-8'),
        'function X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()',
        'function X4LAN_REGISTRY_ENROLL_AND_SEAT_TICK()')
    dispatcher.write_text(text + '\nfunction X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()\n'
        ' X4LAN_REGISTRY_ENROLL_AND_SEAT_TICK()\n X4LAN_REGISTRY_SAVE_BRIDGE_TICK()\nend\n', encoding='utf-8')
    world = ui / 'authority_world_bridge_probe.lua'
    text = world.read_text(encoding='utf-8').replace('X4AuthorityCheckpointMarker', 'X4AuthorityPlayerFixtureMarker')
    text = seat.replace_once(text, ' if not C.IsPlayerValid() then return end\n',
        ' if not X4LAN_REGISTRY_SAVE_READY() then return end\n if not C.IsPlayerValid() then return end\n')
    text = seat.replace_once(text, "SetScript('onUpdate',function()\n", 'function X4LAN_REGISTRY_SAVE_BRIDGE_TICK()\n')
    text = seat.replace_once(text, " if not ok then stopped=true;DebugError('[X4LAN] AUTH_WORLD_BRIDGE ERROR '..tostring(err)) end\nend)\n",
        " if not ok then stopped=true;DebugError('[X4LAN] AUTH_WORLD_BRIDGE ERROR '..tostring(err)) end\nend\n")
    world.write_text(text, encoding='utf-8')
    manifest = lab / 'ui.xml'
    hook = '    <file name="ui/authority_recovery_probe.lua" />\n'
    entries = ''.join('    <file name="ui/' + path.name + '" />\n' for path in additions)
    manifest.write_text(seat.replace_once(manifest.read_text(encoding='utf-8'), hook, entries + hook), encoding='utf-8')
    text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'):
        raise ValueError('unexpected recovery configuration')
    config.write_text(text[:-2] + ',authority_world_bridge=true,authority_marker_required=true,'
        f'authority_control_port={port},authority_control_lease="{lease}",authority_world_epoch="{world_epoch}"' + '}\n', encoding='ascii')
    return config, [*protected, *additions, native]


def save_registered_fixture(*, profile, out, game, identity, deadline, guard,
                            control_socket, lease, world_epoch, state):
    executable = (game / 'X4').stat()
    process_identity = {'pid': identity[0], 'start_ticks': identity[1],
                        'exe_dev': executable.st_dev, 'exe_ino': executable.st_ino}
    hello = f'HELLO|{lease}|{world_epoch}'.encode('ascii')
    peer = None
    while peer is None:
        guard()
        try:
            packet, address = control_socket.recvfrom(769)
        except socket.timeout:
            continue
        guard()
        if packet != hello or not socket_owner(address, control_socket.getsockname(), process_identity):
            raise ValueError('private save bridge peer differs from owned X4')
        peer = address
    previous_log = None

    def checked():
        nonlocal previous_log
        guard()
        if not socket_owner(peer, control_socket.getsockname(), process_identity):
            raise RuntimeError('private save bridge socket ownership changed')
        while True:
            captured = fixture_log.capture(profile / 'engine-output.log', previous_log, 32 << 20)
            if captured is None:
                raise ValueError('fixture log unavailable')
            raw, previous_log, _ = captured
            if raw.endswith(b'\n'):
                break
            guard()
            time.sleep(.02)
        seat.check_control_log(raw, partial=False)
        registry.check_registry_log(raw, partial=False)
        if b'[x4lan] auth_world_bridge error' in raw.lower():
            raise ValueError('private save bridge reported a fault')
        guard()

    checked()
    checkpoint_directory = out / 'checkpoints'
    checkpoint_directory.mkdir(mode=0o700)
    store = CheckpointStore(checkpoint_directory)
    bridge = PlayerRegistryCheckpointBridge(
        enabled=True, sock=control_socket, peer=peer, lease=lease, world_epoch=world_epoch,
        profile=profile, store=store, verify_checkpoint=read_cycle_evidence, marker_required=True,
        fixture_epoch=seat.fixture_source.fixture_save.base.archive.REGISTRY_EPOCH,
        timeout=min(130, max(.001, deadline - time.monotonic())))

    def before_exchange():
        checked()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('registered fixture save deadline')
        bridge._timeout = min(130, remaining)

    before_exchange()
    bridge.pause()
    before_exchange()
    state['save_attempted'] = True
    saved_path = bridge.save_fixture_experiment(enabled=True)
    checked()
    checkpoint = store.publish(saved_path, marker=bridge.pending_marker)
    before_exchange()
    if bridge.checkpoint_published(checkpoint) is not True:
        raise RuntimeError('registered fixture native confirmation failed')
    checked()
    state['verified'] = (store, checkpoint)
    return {'checkpoint_id': checkpoint.checkpoint_id, 'sha256': checkpoint.sha256,
            'saved_fixture_registry_mapping_checked': True, 'checkpoint_confirmed': False,
            'seat_free_proven': False, 'exact_loaded_file_proven': False, 'multiplayer_proven': False}


def run(args):
    lease, world_epoch = secrets.token_hex(16), secrets.token_hex(16)
    control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    control_socket.bind(('127.0.0.1', 0))
    control_socket.settimeout(.25)
    state = {'save_attempted': False, 'verified': None}
    original_install = registry.install
    original_callback = recovery.observation_callback

    def install_private(case, profile, scripts, **kwargs):
        return install_save_bridge(case, profile, scripts, port=control_socket.getsockname()[1],
                                   lease=lease, world_epoch=world_epoch,
                                   registry_installer=original_install, **kwargs)

    def save(**kwargs):
        return save_registered_fixture(**kwargs, control_socket=control_socket, lease=lease,
                                       world_epoch=world_epoch, state=state)

    try:
        registry.install = install_private
        recovery.observation_callback = save
        result = registry.run(args)
    finally:
        registry.install = original_install
        recovery.observation_callback = original_callback
        control_socket.close()
    result.update(scope='one isolated Linux X4; registered fixture checkpoint experiment',
                  checkpoint_requested=state['save_attempted'], save_attempted=state['save_attempted'],
                  checkpoint_confirmed=False, confirmation_attempted=False,
                  checkpoint_confirmation_uncertain=False, saved_registry_mapping_verified=False,
                  multiplayer_proven=False)
    if result.get('success') is True:
        try:
            if state['verified'] is None or not isinstance(result.get('experiment'), dict):
                raise ValueError('verified registered fixture checkpoint missing')
            store, checkpoint = state['verified']
            result['confirmation_attempted'] = True
            try:
                store.confirm(checkpoint)
            except BaseException:
                result['checkpoint_confirmation_uncertain'] = True
                raise
            result['checkpoint_confirmed'] = True
            result['saved_registry_mapping_verified'] = True
            result['experiment']['checkpoint_confirmed'] = True
        except BaseException as error:
            result.update(success=False, error='checkpoint finalization: ' + (str(error) or type(error).__name__))
    output = Path(args.out) / 'registry-save-result.json'
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--display', required=True)
    parser.add_argument('--slot', type=int, choices=(1, 2), required=True)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--seed', type=int, default=276944566)
    try:
        result = run(parser.parse_args())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
