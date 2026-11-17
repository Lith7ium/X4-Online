#!/usr/bin/env python3
"""Opt-in disposable Linux fixture-save experiment; import never starts X4.

This prepares one unregistered two-ship fixture, then saves and checks its
serialized references. It is not admission, player control, or multiplayer.
"""
import argparse
import hashlib
import json
import math
import os
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
from authority_player_fixture_bridge import PlayerFixtureBridge
import authority_sector_read_live as base
from authority_tcp_job_client_live import socket_owner

TAG = '[X4LAN] AUTH_PLAYER_FIXTURE_SAVE '
ARCHIVED_LOAD_SLOT = 'save_009'
PRIVATE_LOAD_SLOT = 'save_008'
SECTOR_READ_SLOT = 2
HISTORICAL_REGISTRY = ROOT / 'tools/dev/fixtures/census-20261115/authority_ship_registry.xml'
HISTORICAL_REGISTRY_SHA256 = '8b7c9887c9c1476e45fe84a60243547d96e09b11d4c40fabd151930af517e939'
_BASE_CHECK = base.check_log_bytes
_BASE_FAULT = base.fault_log


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('private experiment hook missing or ambiguous')
    return text.replace(old, new)


def historical_registry():
    """Select only the reviewed registry matching this archived checkpoint."""
    contents = base._read_regular(HISTORICAL_REGISTRY, 1 << 20)
    if hashlib.sha256(contents).hexdigest() != HISTORICAL_REGISTRY_SHA256:
        raise ValueError('historical registry script differs from pinned fixture')
    return HISTORICAL_REGISTRY


def install(case, profile, ticket, slot, *, port, lease, world_epoch, nonce, registry_script=None):
    if slot != SECTOR_READ_SLOT or ticket['slot'] != ARCHIVED_LOAD_SLOT:
        raise ValueError('expected archived sector-read ticket')
    if registry_script is not None and Path(registry_script) != historical_registry():
        raise ValueError('fixture install requires the pinned historical registry')
    ticket['slot'] = PRIVATE_LOAD_SLOT
    if registry_script is None:
        protected = base.install(case, profile, ticket, slot)
    else:
        protected = base.install(case, profile, ticket, slot, registry_script=registry_script)
    lab = case / 'extensions/x4_lan_lab'
    md, ui = lab / 'md', lab / 'ui'
    copies = {
        ROOT / 'tools/dev/authority_player_sector_fixture.xml': md / 'authority_player_sector_fixture.xml',
        ROOT / 'tools/dev/authority_player_seat_experiment.xml': md / 'authority_player_seat_experiment.xml',
        ROOT / 'tools/dev/authority_player_fixture_marker.xml': md / 'authority_player_fixture_marker.xml',
        ROOT / 'tools/dev/authority_player_fixture_save_probe.lua': ui / 'authority_player_fixture_save_probe.lua',
        ROOT / 'src/authority/lua/control_state.lua': ui / 'authority_control_state.lua',
        ROOT / 'src/authority/lua/x4_control_engine.lua': ui / 'x4_control_engine.lua',
        ROOT / 'src/authority/lua/local_control_bridge.lua': ui / 'local_control_bridge.lua',
        ROOT / 'tools/dev/authority_world_bridge_probe.lua': ui / 'authority_world_bridge_probe.lua',
    }
    for source, target in copies.items():
        if target.exists() or target.is_symlink():
            raise ValueError('private fixture file already exists')
        shutil.copyfile(source, target)
    compiler = shutil.which('cc')
    if not compiler:
        raise ValueError('C compiler required for private UDP module')
    native = lab / 'native/x4lan_net.so'
    subprocess.run(
        [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
         str(ROOT / 'src/native/net.c'), '-ldl', '-o', str(native)],
        check=True, capture_output=True,
    )
    config = ui / 'config.lua'
    text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'):
        raise ValueError('unexpected private configuration')
    config.write_text(text[:-2] + ',authority_player_fixture_save=true,authority_player_fixture_timeout=120,'
        f'authority_player_fixture_nonce="{nonce}",authority_world_bridge=true,authority_marker_required=true,'
        f'authority_control_port={port},authority_control_lease="{lease}",authority_world_epoch="{world_epoch}"' + '}\n', encoding='ascii')
    manifest = lab / 'ui.xml'
    hook = '    <file name="ui/authority_download_load_probe.lua" />\n'
    additions = ''.join('    <file name="ui/' + name + '" />\n' for name in (
        'authority_player_fixture_save_probe.lua', 'authority_control_state.lua', 'x4_control_engine.lua',
        'local_control_bridge.lua', 'authority_world_bridge_probe.lua'))
    manifest.write_text(replace_once(manifest.read_text(encoding='utf-8'), hook, additions + hook), encoding='utf-8')
    owner = ui / 'authority_download_load_probe.lua'
    text = replace_once(owner.read_text(encoding='utf-8'), ' if state==\'done\' then return end\n',
        " if state=='done' then X4LAN_PLAYER_FIXTURE_SAVE_TICK();X4LAN_PLAYER_WORLD_BRIDGE_TICK();return end\n")
    owner.write_text(text, encoding='utf-8')
    world = ui / 'authority_world_bridge_probe.lua'
    text = world.read_text(encoding='utf-8').replace('X4AuthorityCheckpointMarker', 'X4AuthorityPlayerFixtureMarker')
    text = replace_once(text, ' if not C.IsPlayerValid() then return end\n',
                        ' if not X4LAN_PLAYER_FIXTURE_SAVE_READY() then return end\n if not C.IsPlayerValid() then return end\n')
    text = replace_once(text, "SetScript('onUpdate',function()\n", 'function X4LAN_PLAYER_WORLD_BRIDGE_TICK()\n')
    text = replace_once(text, " if not ok then stopped=true;DebugError('[X4LAN] AUTH_WORLD_BRIDGE ERROR '..tostring(err)) end\nend)\n",
                        " if not ok then stopped=true;DebugError('[X4LAN] AUTH_WORLD_BRIDGE ERROR '..tostring(err)) end\nend\n")
    world.write_text(text, encoding='utf-8')
    return protected + list(copies.values()) + [native]


def fault(raw):
    lower = raw.lower()
    return (_BASE_FAULT(raw) or (TAG + 'ERROR').lower().encode() in lower or
            b'[x4lan] auth_world_bridge error' in lower or
            b'error while parsing expression:' in lower or b'maximum operator nesting level reached' in lower or
            b'could not find suitable data type for conversion!' in lower or
            b'invalid data types for arithmetic operation!' in lower)


def validate(raw, ticket, slot, *, partial=False):
    if fault(raw):
        raise ValueError('fixture save probe reported a fault')
    if not raw.endswith(b'\n') and partial:
        return None
    lines = raw.decode('utf-8').splitlines()
    rows = [(i, line.split(TAG, 1)[1].strip()) for i, line in enumerate(lines) if TAG in line]
    expected = ('PREFLIGHT', 'CREATED')
    if len(rows) > len(expected) or any(value != expected[i] for i, (_, value) in enumerate(rows)):
        raise ValueError('invalid fixture creation receipts')
    pause_tag = base.load.TAG.decode() + 'pause_observed|'
    pauses = [i for i, line in enumerate(lines) if pause_tag in line]
    if rows and (len(pauses) != 1 or rows[0][0] <= pauses[0]):
        raise ValueError('fixture created before pause')
    result = _BASE_CHECK(raw, ticket, slot, partial=partial)
    if result is None:
        return None
    if len(rows) != len(expected):
        if partial:
            return None
        raise ValueError('fixture creation receipts incomplete')
    result.update(fixture_created_receipt=True, fixture_registry_enrollment_proven=False,
                  seat_free_proven=False, multiplayer_proven=False)
    return result


def run(args):
    if args.slot != SECTOR_READ_SLOT or not math.isfinite(args.timeout) or args.timeout < 60:
        raise ValueError('fixture save experiment requires slot 2 and at least 60 seconds')
    historical_registry()
    source_store_directory = base.base.local_directory(args.store)
    original_source_fingerprints = base.archive._path_fingerprints(source_store_directory)
    control_lease, world_epoch, fixture_request_nonce = (secrets.token_hex(16) for _ in range(3))
    control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    control_socket.bind(('127.0.0.1', 0))
    control_socket.settimeout(.25)
    save_attempted = False
    verified_checkpoints = ()
    original_install = base.install
    original_check_origin_scripts = base.check_origin_scripts
    original_check_log_bytes = base.check_log_bytes
    original_fault_log = base.fault_log
    original_observation_callback = base.observation_callback
    original_result_finalizer = base.result_finalizer
    original_stage_checkpoint = base.base.stage_checkpoint

    def stage(store, checkpoint_id, profile):
        checkpoint, staged_source = original_stage_checkpoint(store, checkpoint_id, profile)
        staged_load = staged_source.with_name(PRIVATE_LOAD_SLOT + '.xml.gz')
        os.link(staged_source, staged_load, follow_symlinks=False)
        staged_source.unlink()
        return checkpoint, staged_load

    def install_private(case, profile, ticket, slot):
        installed_hook = base.install
        try:
            base.install = original_install
            return install(
                case, profile, ticket, slot, port=control_socket.getsockname()[1],
                lease=control_lease, world_epoch=world_epoch, nonce=fixture_request_nonce,
                registry_script=historical_registry(),
            )
        finally:
            base.install = installed_hook

    def check_historical_origin(store, profile):
        return original_check_origin_scripts(store, profile, registry_script=historical_registry())

    def save(*, profile, out, game, identity, deadline, guard):
        nonlocal save_attempted, verified_checkpoints
        game_stat = (game / 'X4').stat()
        process_identity = {
            'pid': identity[0], 'start_ticks': identity[1],
            'exe_dev': game_stat.st_dev, 'exe_ino': game_stat.st_ino,
        }
        expected_hello = f'HELLO|{control_lease}|{world_epoch}'.encode('ascii')
        peer = None
        while peer is None:
            guard()
            if time.monotonic() >= deadline:
                raise TimeoutError('fixture bridge enrollment timed out')
            try:
                packet, address = control_socket.recvfrom(769)
            except socket.timeout:
                continue
            guard()
            if packet != expected_hello or not socket_owner(address, control_socket.getsockname(), process_identity):
                raise ValueError('fixture bridge peer differs from owned X4')
            peer = address

        def checked():
            guard()
            if not socket_owner(peer, control_socket.getsockname(), process_identity):
                raise RuntimeError('fixture bridge socket ownership changed')
            raw = base.stable_read(profile / 'engine-output.log', 32 << 20, collect=True)[2]
            if fault(raw):
                raise RuntimeError('fixture probe fault after creation')
            guard()

        checked()
        checkpoint_directory = out / 'checkpoints'
        checkpoint_directory.mkdir(mode=0o700)
        store = CheckpointStore(checkpoint_directory)
        adapter = PlayerFixtureBridge(
            enabled=True, sock=control_socket, peer=peer, lease=control_lease, world_epoch=world_epoch,
            profile=profile, store=store, verify_checkpoint=read_cycle_evidence, marker_required=True,
            fixture_epoch=base.archive.REGISTRY_EPOCH, timeout=min(130, max(.001, deadline - time.monotonic())),
        )

        def before_exchange():
            checked()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('fixture save deadline')
            adapter._timeout = min(130, remaining)

        before_exchange()
        # The native controller requires its own settled-pause receipt even
        # though the load and fixture probes already observed a paused game.
        adapter.pause()
        before_exchange()
        save_attempted = True
        saved_path = adapter.save_fixture_experiment(enabled=True)
        checked()
        checkpoint = store.publish(saved_path, marker=adapter.pending_marker)
        before_exchange()
        if adapter.checkpoint_published(checkpoint) is not True:
            raise RuntimeError('fixture confirmation failed')
        checked()
        verified_checkpoints += ((store, checkpoint),)
        return {
            'checkpoint_id': checkpoint.checkpoint_id,
            'sha256': checkpoint.sha256,
            'saved_fixture_references_checked': True,
            'fixture_registry_enrollment_proven': False,
            'checkpoint_confirmed': False,
            'seat_free_proven': False,
            'exact_loaded_file_proven': False,
            'multiplayer_proven': False,
        }

    def finalize(result):
        result.update(checkpoint_requested=save_attempted, save_attempted=save_attempted,
                      checkpoint_confirmed=False, confirmation_attempted=False,
                      checkpoint_confirmation_uncertain=False)
        if base.archive._path_fingerprints(source_store_directory) != original_source_fingerprints:
            raise ValueError('checkpoint source changed')
        result.update(scope='one isolated Linux X4; experimental fixture serialization only',
                      fixture_registry_enrollment_proven=False, seat_free_proven=False, multiplayer_proven=False)
        if result.get('success') is True:
            if len(verified_checkpoints) != 1 or not isinstance(result.get('experiment'), dict):
                raise ValueError('verified fixture checkpoint missing')
            store, checkpoint = verified_checkpoints[0]
            result['confirmation_attempted'] = True
            try:
                store.confirm(checkpoint)
            except BaseException:
                # A failing fsync can follow a visible pointer replacement.
                result['checkpoint_confirmation_uncertain'] = True
                raise
            result['checkpoint_confirmed'] = True
            result['experiment']['checkpoint_confirmed'] = True

    try:
        base.install = install_private
        base.check_origin_scripts = check_historical_origin
        base.check_log_bytes = validate
        base.fault_log = fault
        base.observation_callback = save
        base.result_finalizer = finalize
        base.base.stage_checkpoint = stage
        return base.run(args)
    finally:
        base.install = original_install
        base.check_origin_scripts = original_check_origin_scripts
        base.check_log_bytes = original_check_log_bytes
        base.fault_log = original_fault_log
        base.observation_callback = original_observation_callback
        base.result_finalizer = original_result_finalizer
        base.base.stage_checkpoint = original_stage_checkpoint
        control_socket.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--store', type=Path, default=base.archive.DEFAULT_STORE)
    parser.add_argument('--display', required=True)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--seed', type=int, default=276944566)
    args = parser.parse_args()
    args.slot = SECTOR_READ_SLOT
    try:
        result = run(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
