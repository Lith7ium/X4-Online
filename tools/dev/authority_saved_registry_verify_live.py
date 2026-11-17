#!/usr/bin/env python3
"""Reload a confirmed fixture save and read its two registry mappings in X4.

This opt-in isolated diagnostic neither enrolls nor teleports ships and does
not exercise the legacy Resolve cue, admission, flight or multiplayer.
"""
import argparse
import json
from pathlib import Path
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.checkpoints import CheckpointStore, _read_regular
import authority_fixture_checkpoint_source as fixture_source
import authority_recovery_live as recovery
import authority_saved_fixture_log as fixture_log
import authority_saved_player_control_live as seat
import authority_saved_registry_checkpoint_source as source

TAG = '[X4LAN] AUTH_SAVED_REGISTRY_VERIFY '


def check_log(raw, *, partial):
    if not raw.endswith(b'\n'):
        if partial:
            return False
        raise ValueError('incomplete registry verification log')
    lower = raw.lower()
    if any(fault in lower for fault in (b'error while parsing expression:',
            b'maximum operator nesting level reached', b'could not find suitable data type for conversion!',
            b'invalid data types for arithmetic operation!', b'error in md cue md.x4authority',
            b'error in lua script', b'stack traceback:')):
        raise ValueError('registry verification reported an engine fault')
    lines = raw.decode('utf-8').splitlines()
    values = [(index, line.split(TAG, 1)[1].strip()) for index, line in enumerate(lines) if TAG in line]
    if len(values) > 1 or (values and values[0][1] != 'MATCHED 4 3 4'):
        raise ValueError('registry verification fault or duplicate result')
    pauses = [index for index, line in enumerate(lines) if '[X4LAN] AUTH_RECOVERY PAUSED' in line]
    if values and (len(pauses) != 1 or values[0][0] <= pauses[0]):
        raise ValueError('registry verification occurred before recovery pause')
    if not values and not partial:
        raise ValueError('registry verification result missing')
    return bool(values)


class RegistryVerifyWatch(recovery.RecoveryWatch):
    def __init__(self, path, marker):
        super().__init__(path, marker)
        self.snapshot = None

    def poll(self):
        caught_up = super().poll()
        captured = fixture_log.capture(self.path, self.snapshot, 32 << 20)
        if captured is None:
            return False
        raw, self.snapshot, stable = captured
        verified = check_log(raw, partial=True)
        return caught_up and stable and self.stage == 3 and verified


def install(case, profile, scripts, *, nonce, timeout, original_install):
    if set(scripts) != set(fixture_source.SAVED_SCRIPTS):
        raise ValueError('saved MD script set differs')
    config = original_install(case, profile)
    lab = case / 'extensions/x4_lan_lab'
    ui, md = lab / 'ui', lab / 'md'
    for name, contents in scripts.items():
        (md / name).write_bytes(contents)
    cue, owner = md / 'authority_saved_registry_verify.xml', ui / 'authority_saved_registry_verify_owner.lua'
    shutil.copyfile(ROOT / 'tools/dev/authority_saved_registry_verify.xml', cue)
    shutil.copyfile(ROOT / 'tools/dev/authority_saved_registry_verify_owner.lua', owner)
    marker = ui / 'authority_checkpoint_marker_probe.lua'
    marker_text = marker.read_text(encoding='utf-8')
    if 'X4AuthorityCheckpointMarker' not in marker_text:
        raise ValueError('fixture marker probe hook missing')
    marker.write_text(marker_text.replace('X4AuthorityCheckpointMarker', 'X4AuthorityPlayerFixtureMarker'),
                      encoding='utf-8')
    recovery_owner = ui / 'authority_recovery_probe.lua'
    recovery_owner.write_text(seat.replace_once(recovery_owner.read_text(encoding='utf-8'),
        " if state=='done' then return end\n",
        " if state=='done' then X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK();return end\n"), encoding='utf-8')
    manifest = lab / 'ui.xml'
    hook = '    <file name="ui/authority_recovery_probe.lua" />\n'
    manifest.write_text(seat.replace_once(manifest.read_text(encoding='utf-8'), hook,
        '    <file name="ui/authority_saved_registry_verify_owner.lua" />\n' + hook), encoding='utf-8')
    text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'):
        raise ValueError('unexpected recovery configuration')
    epoch = fixture_source.fixture_save.base.archive.REGISTRY_EPOCH
    config.write_text(text[:-2] + ',authority_saved_registry_verify=true,'
        f'authority_saved_registry_nonce="{nonce}",authority_fixture_epoch="{epoch}",'
        f'authority_saved_registry_timeout={timeout:.17g}' + '}\n', encoding='ascii')
    return config, [*(md / name for name in scripts), cue, owner]


def run(args):
    if args.timeout < 60:
        raise ValueError('at least 60 seconds required')
    source_store = recovery.base.local_directory(args.store)
    original_stage, original_verify = recovery.stage_confirmed_recovery, recovery.verify_source
    original_install, original_watch = recovery.install_probe, recovery.RecoveryWatch
    original_protected, original_finalizer = recovery.extra_protected_files, recovery.result_finalizer
    scripts = checkpoint = source_result = extra_files = None
    nonce = secrets.token_hex(16)

    def stage(store, profile):
        return original_stage(store, profile, marker_script='X4AuthorityPlayerFixtureMarker')

    def verify(store_directory, selected, profile):
        nonlocal scripts, checkpoint, source_result
        scripts = source.verify(store_directory, selected, profile)
        checkpoint = selected
        source_result = _read_regular(source_store.parent / 'registry-save-result.json', 65536)

    def install_private(case, profile):
        nonlocal extra_files
        if scripts is None:
            raise ValueError('registered fixture source was not verified')
        config, extra_files = install(case, profile, scripts, nonce=nonce, timeout=min(args.timeout, 120),
                                      original_install=original_install)
        return config

    def protected(_case, _profile):
        if extra_files is None:
            raise ValueError('registry verification files not installed')
        return extra_files

    def finalize(result):
        if checkpoint is None:
            if result.get('success') is True:
                raise ValueError('registered fixture source not verified')
            return
        if (CheckpointStore(source_store).latest_marked_confirmed() != checkpoint or
                _read_regular(source_store.parent / 'registry-save-result.json', 65536) != source_result):
            raise ValueError('registered fixture checkpoint source changed')
        source_md = source_store.parent / 'case/extensions/x4_lan_lab/md'
        if any(_read_regular(source_md / name, 1 << 20) != contents for name, contents in scripts.items()):
            raise ValueError('registered fixture saved MD source changed')
        result.update(scope='one isolated Linux X4; read-only saved fixture registry mapping',
                      runtime_fixture_mapping_observed=result.get('success') is True,
                      legacy_resolve_invoked=False, registry_enrollment_attempted=False,
                      player_seat_changed=False, exact_loaded_file_proven=False,
                      multiplayer_proven=False)

    try:
        recovery.stage_confirmed_recovery = stage
        recovery.verify_source = verify
        recovery.install_probe = install_private
        recovery.RecoveryWatch = RegistryVerifyWatch
        recovery.extra_protected_files = protected
        recovery.result_finalizer = finalize
        return recovery.run(args)
    finally:
        recovery.stage_confirmed_recovery = original_stage
        recovery.verify_source = original_verify
        recovery.install_probe = original_install
        recovery.RecoveryWatch = original_watch
        recovery.extra_protected_files = original_protected
        recovery.result_finalizer = original_finalizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--display', required=True)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--seed', type=int, default=276944566)
    try:
        result = run(parser.parse_args())
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
