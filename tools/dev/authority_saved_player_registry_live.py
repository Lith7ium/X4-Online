#!/usr/bin/env python3
"""Private saved-fixture enrollment followed by a single seat observation.

This uses the historical registry without changing saved MD scripts. It does
not save the newly registered state or establish multiplayer.
"""
import argparse
import json
from pathlib import Path
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_saved_player_control_live as seat

REGISTRY_TAG = '[X4LAN] AUTH_PLAYER_REGISTRY '
EXPECTED_RECEIPT = 'ENROLLED 3 4'


def check_registry_log(raw, *, partial):
    """Require one completed enrollment between recovery pause and seat start."""
    if not raw.endswith(b'\n'):
        if partial:
            return False
        raise ValueError('incomplete registry log')
    lines = raw.decode('utf-8').splitlines()
    receipts = [(number, line.split(REGISTRY_TAG, 1)[1].strip())
                for number, line in enumerate(lines) if REGISTRY_TAG in line]
    if len(receipts) > 1 or (receipts and receipts[0][1] != EXPECTED_RECEIPT):
        raise ValueError('fixture registry reported a fault or duplicate receipt')
    if not receipts:
        if partial:
            return False
        raise ValueError('fixture registry receipt missing')
    pauses = [number for number, line in enumerate(lines) if '[X4LAN] AUTH_RECOVERY PAUSED' in line]
    starts = [number for number, line in enumerate(lines) if seat.CONTROL_TAG + 'START' in line]
    if len(pauses) != 1 or receipts[0][0] <= pauses[0]:
        raise ValueError('fixture registry enrollment precedes recovery pause')
    if starts and (len(starts) != 1 or receipts[0][0] >= starts[0]):
        raise ValueError('fixture seat started before registry enrollment')
    return True


class SavedRegistryWatch(seat.SavedControlWatch):
    """Add a registry receipt to the existing marker, pause and seat checks."""
    def validate_snapshot(self, raw):
        seat_complete = super().validate_snapshot(raw)
        registration_complete = check_registry_log(raw, partial=True)
        return seat_complete and registration_complete


def install(case, profile, scripts, *, slot, nonce, timeout, seat_installer, recovery_installer, registry_nonce):
    config, protected = seat_installer(case, profile, scripts, slot=slot, nonce=nonce,
                                      timeout=timeout, original_install=recovery_installer)
    lab = case / 'extensions/x4_lan_lab'
    ui, md = lab / 'ui', lab / 'md'
    seat_owner = ui / 'authority_saved_player_control_owner.lua'
    seat_owner.write_text(seat.replace_once(seat_owner.read_text(encoding='utf-8'),
        'function X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()',
        'function X4LAN_AUTHORITY_RECOVERY_SEAT_TICK()'), encoding='utf-8')

    registry_client = ui / 'authority_ship_registry_client.lua'
    source = (ROOT / 'src/authority/lua/ship_registry_client.lua').read_text(encoding='utf-8')
    registry_client.write_text(seat.replace_once(source, '\nreturn M\n',
                               '\nX4LAN_SHIP_REGISTRY_CLIENT=M\nreturn M\n'), encoding='utf-8')
    additions = [registry_client]
    for name in ('authority_player_registry_enroll.lua', 'authority_saved_player_registry_dispatch.lua'):
        target = ui / name
        shutil.copyfile(ROOT / 'tools/dev' / name, target)
        additions.append(target)
    read_cue = md / 'authority_player_registry_read.xml'
    shutil.copyfile(ROOT / 'tools/dev/authority_player_registry_read.xml', read_cue)
    manifest = lab / 'ui.xml'
    hook = '    <file name="ui/authority_recovery_probe.lua" />\n'
    entries = ''.join('    <file name="ui/' + path.name + '" />\n' for path in additions)
    manifest.write_text(seat.replace_once(manifest.read_text(encoding='utf-8'), hook, entries + hook),
                        encoding='utf-8')
    text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'):
        raise ValueError('unexpected registry recovery configuration')
    config.write_text(text[:-2] + ',authority_saved_player_registry=true,'
                      f'authority_registry_enroll_nonce="{registry_nonce}"' + '}\n', encoding='ascii')
    return config, [*protected, *additions, read_cue]


def run(args):
    original_seat_install = seat.install
    original_watch = seat.SavedControlWatch
    registry_nonce = secrets.token_hex(16)

    def install_registry(case, profile, scripts, *, slot, nonce, timeout, original_install):
        return install(case, profile, scripts, slot=slot, nonce=nonce, timeout=timeout,
                       seat_installer=original_seat_install, recovery_installer=original_install,
                       registry_nonce=registry_nonce)

    try:
        seat.install = install_registry
        seat.SavedControlWatch = SavedRegistryWatch
        result = seat.run(args)
    finally:
        seat.install = original_seat_install
        seat.SavedControlWatch = original_watch
    result.update(scope='one isolated Linux X4; runtime fixture enrollment and seat observation',
                  registry_enrollment_observed=result.get('success') is True,
                  saved_registry_mapping_verified=False, multiplayer_proven=False)
    output = Path(args.out) / 'registry-result.json'
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
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
