#!/usr/bin/env python3
"""One opt-in local X4 offset observation from a pinned fixture checkpoint.

This starts only when invoked explicitly. It does not distribute a save, use a
client pose, prove cross-process frames, or claim a persistent movement.
"""
import argparse
import json
import math
import re
import secrets
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_fixture_checkpoint_source as fixture_source
import authority_fixture_frame_pair_live as frames
import authority_recovery_live as recovery
import authority_saved_fixture_log as fixture_log
import authority_saved_player_control_live as seat
import authority_saved_registry_checkpoint_source as source

TAG = b'[X4LAN] AUTH_FIXTURE_LOCAL_OFFSET '
MARKER = 'X4AuthorityPlayerFixtureMarker'


def parse_log(raw, nonce, slot, *, partial):
    """Validate a unique ordered pause/write/immediate-readback receipt."""
    if not isinstance(raw, bytes) or not re.fullmatch(r'[0-9a-f]{32}', nonce) or slot not in (1, 2):
        raise ValueError('invalid local offset log context')
    if not raw.endswith(b'\n'):
        if partial:
            return None
        raise ValueError('incomplete local offset log')
    lowered = raw.lower()
    faults = (b'error while parsing expression:', b'maximum operator nesting level reached',
              b'error in md cue md.x4authority', b'error in lua script', b'stack traceback:',
              b'[x4lan] auth_recovery error', b'[x4lan] auth_fixture_local_offset error')
    if any(fault in lowered for fault in faults):
        raise ValueError('local offset runtime fault')
    pause_lines, receipts = [], []
    for number, line in enumerate(raw.splitlines()):
        if b'[X4LAN] AUTH_RECOVERY PAUSED' in line:
            pause_lines.append(number)
        if TAG in line:
            try:
                receipts.append((number, line.split(TAG, 1)[1].strip().decode('ascii')))
            except UnicodeDecodeError as error:
                raise ValueError('invalid local offset receipt') from error
    if not receipts:
        if partial:
            return None
        raise ValueError('local offset receipt missing')
    if len(pause_lines) != 1 or receipts[0][0] <= pause_lines[0] or len(receipts) > 2:
        raise ValueError('local offset receipt order invalid')
    if receipts[0][1] != 'WRITE_ENTERED ' + nonce:
        raise ValueError('local offset write intent differs')
    if len(receipts) == 1:
        if partial:
            return None
        raise ValueError('immediate readback missing')
    values = receipts[1][1].split()
    if len(values) != 10 or values[:3] != ['OBSERVED', nonce, str(slot + 2)]:
        raise ValueError('local offset observation differs')
    try:
        before_x, before_y, before_z, after_x, after_y, after_z, distance = map(float, values[3:])
    except ValueError as error:
        raise ValueError('invalid local offset coordinate') from error
    if not all(math.isfinite(value) and abs(value) <= 1e7 for value in
               (before_x, before_y, before_z, after_x, after_y, after_z, distance)):
        raise ValueError('invalid local offset coordinate')
    measured_distance = math.dist((after_x, after_y, after_z), (before_x + 10, before_y, before_z))
    if (distance < 0 or abs(distance - measured_distance) > 1e-5 or measured_distance > 0.5):
        raise ValueError('immediate local offset not observed')
    return {'index': slot + 2, 'before': [before_x, before_y, before_z],
            'after': [after_x, after_y, after_z], 'target_distance': measured_distance}


def install(case, profile, scripts, *, nonce, slot, original_install):
    if set(scripts) != set(fixture_source.SAVED_SCRIPTS) or slot not in (1, 2):
        raise ValueError('saved fixture scripts or slot differ')
    config = original_install(case, profile)
    lab = case / 'extensions/x4_lan_lab'
    ui, md = lab / 'ui', lab / 'md'
    for name, contents in scripts.items():
        (md / name).write_bytes(contents)
    shutil.copyfile(ROOT / 'tools/dev/authority_fixture_local_offset.xml', md / 'authority_fixture_local_offset.xml')
    for name in ('authority_registry_resolve_string.lua', 'authority_fixture_local_offset_bootstrap.lua'):
        shutil.copyfile(ROOT / 'tools/dev' / name, ui / name)
    lua = (ROOT / 'tools/dev/authority_fixture_local_offset.lua').read_text(encoding='utf-8')
    if not lua.endswith('return M\n'):
        raise ValueError('local offset owner export changed')
    (ui / 'authority_fixture_local_offset.lua').write_text(
        lua[:-len('return M\n')] + 'X4LAN_FIXTURE_LOCAL_OFFSET = M\nreturn M\n', encoding='utf-8')
    marker = ui / 'authority_checkpoint_marker_probe.lua'
    marker_text = marker.read_text(encoding='utf-8')
    if marker_text.count('X4AuthorityCheckpointMarker') != 5:
        raise ValueError('fixture marker probe changed')
    marker.write_text(marker_text.replace('X4AuthorityCheckpointMarker', MARKER), encoding='utf-8')
    owner = ui / 'authority_recovery_probe.lua'
    owner.write_text(seat.replace_once(owner.read_text(encoding='utf-8'),
        " if state=='done' then return end\n",
        " if state=='done' then X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK();return end\n"), encoding='utf-8')
    manifest = lab / 'ui.xml'
    hook = '    <file name="ui/authority_recovery_probe.lua" />\n'
    manifest.write_text(seat.replace_once(manifest.read_text(encoding='utf-8'), hook,
        '    <file name="ui/authority_registry_resolve_string.lua" />\n'
        '    <file name="ui/authority_fixture_local_offset.lua" />\n'
        '    <file name="ui/authority_fixture_local_offset_bootstrap.lua" />\n' + hook), encoding='utf-8')
    text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'):
        raise ValueError('unexpected recovery configuration')
    epoch = fixture_source.fixture_save.base.archive.REGISTRY_EPOCH
    if not re.fullmatch(r'[0-9a-f]{32}', nonce) or nonce == epoch:
        raise ValueError('invalid offset nonce')
    config.write_text(text[:-2] + ',authority_local_offset_enabled=true,'
        f'authority_local_offset_epoch="{epoch}",authority_local_offset_nonce="{nonce}",'
        f'authority_local_offset_slot={slot},authority_local_offset_timeout=120' + '}\n', encoding='ascii')
    return config, [*(md / name for name in scripts), md / 'authority_fixture_local_offset.xml',
        ui / 'authority_registry_resolve_string.lua', ui / 'authority_fixture_local_offset.lua',
        ui / 'authority_fixture_local_offset_bootstrap.lua']


def run(args):
    if args.slot not in (1, 2):
        raise ValueError('fixture slot must be 1 or 2')
    if Path(args.store).resolve(strict=True) != frames.SOURCE.resolve(strict=True):
        raise ValueError('only the pinned confirmed fixture source is permitted')
    # Recovery creates its output before staging; protect the source's entire
    # historical server directory, including its private profile and saves.
    output = recovery.snapshot.output_path(args.out)
    if output.resolve().is_relative_to(frames.SOURCE.parent.resolve(strict=True)):
        raise ValueError('output must be outside the fixture source directory')
    nonce = secrets.token_hex(16)
    original = (recovery.stage_confirmed_recovery, recovery.verify_source, recovery.install_probe,
                recovery.RecoveryWatch, recovery.extra_protected_files, recovery.observation_callback,
                recovery.result_finalizer)
    scripts = checkpoint = extra = profile_path = None
    observed = [None]
    last_snapshot = [None]
    engine_log = [None]

    class OffsetWatch(original[3]):
        def poll(self):
            caught = super().poll()
            captured = fixture_log.capture(self.path, last_snapshot[0], 32 << 20)
            if captured is None:
                return False
            raw, last_snapshot[0], stable = captured
            parsed = parse_log(raw, nonce, args.slot, partial=True)
            if parsed is not None:
                if observed[0] is not None and observed[0] != parsed:
                    raise ValueError('local offset observation changed')
                observed[0] = parsed
            return caught and stable and self.stage == 3 and parsed is not None

    def stage(store, profile):
        return original[0](store, profile, marker_script=MARKER)

    def verify(store, selected, profile):
        nonlocal scripts, checkpoint, profile_path
        if selected.checkpoint_id != frames.SOURCE_ID or selected.sha256 != frames.SOURCE_SHA:
            raise ValueError('fixture checkpoint differs from pinned source')
        scripts = source.verify_recovered(store, selected, profile)
        checkpoint, profile_path = selected, profile
        engine_log[0] = profile / 'engine-output.log'

    def install_private(case, profile):
        nonlocal extra
        if scripts is None:
            raise ValueError('fixture source not verified')
        config, extra = install(case, profile, scripts, nonce=nonce, slot=args.slot, original_install=original[2])
        return config

    def protected(_case, _profile):
        if extra is None:
            raise ValueError('local offset files were not installed')
        return extra

    def capture(*, guard, identity, **_kwargs):
        guard()
        if observed[0] is None or type(identity) is not tuple or len(identity) != 2 or any(
                type(value) is not int or value <= 0 for value in identity):
            raise ValueError('owned X4 offset observation unavailable')
        guard()
        return {'local_offset': dict(observed[0]), 'owned_x4_identity': list(identity)}

    def final(result):
        if result.get('success') is not True:
            return
        if (checkpoint is None or observed[0] is None or result.get('owned_processes_remaining') != [] or
                source.verify_recovered(args.store, checkpoint, profile_path) != scripts):
            raise ValueError('source checkpoint or X4 cleanup not confirmed')
        captured = fixture_log.capture(engine_log[0], last_snapshot[0], 32 << 20)
        if captured is None:
            raise ValueError('final local offset log unavailable')
        raw, _, stable = captured
        final_observation = parse_log(raw, nonce, args.slot, partial=False)
        if not stable or final_observation != observed[0]:
            raise ValueError('final local offset observation differs')
        result.update(scope='one disposable paused Linux X4; one local fixture position write',
                      immediate_local_offset_observed=True, delayed_movement_proven=False,
                      collision_clearance_proven=False, client_frame_proven=False,
                      gameplay_proven=False, persistent_write_proven=False)

    try:
        (recovery.stage_confirmed_recovery, recovery.verify_source, recovery.install_probe,
         recovery.RecoveryWatch, recovery.extra_protected_files, recovery.observation_callback,
         recovery.result_finalizer) = (stage, verify, install_private, OffsetWatch, protected, capture, final)
        return recovery.run(SimpleNamespace(game=args.game, store=args.store, out=args.out, display=args.display,
                                            timeout=args.timeout, seed=args.seed))
    finally:
        (recovery.stage_confirmed_recovery, recovery.verify_source, recovery.install_probe,
         recovery.RecoveryWatch, recovery.extra_protected_files, recovery.observation_callback,
         recovery.result_finalizer) = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--display', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--slot', type=int, choices=(1, 2), required=True)
    parser.add_argument('--store', type=Path, default=frames.SOURCE)
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
