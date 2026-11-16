#!/usr/bin/env python3
"""Opt-in single private X4 fixture and seat diagnostic; never requests a save.

Import does not launch X4. The harness performs an experiment in a disposable
profile against one recorded checkpoint. A completed diagnostic does not prove
seat usability, multiplayer, or that the universe was saved.
"""
import argparse
import json
import math
from pathlib import Path
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_sector_read_live as base
import authority_job_attach_live as readonly

TAG = '[X4LAN] AUTH_PLAYER_SEAT_EXPERIMENT '
STEPS = ('PREFLIGHT', 'CREATED', 'POSITIVE', 'NEGATIVE1', 'NEGATIVE2', 'DONE')
MD = ('authority_player_sector_fixture.xml', 'authority_player_seat_calibration.xml',
      'authority_player_seat_experiment.xml')
UI = ('authority_player_seat_calibration.lua', 'authority_player_seat_experiment.lua')
# Preserve the original check even while the private runner temporarily installs
# its stricter combined check in the underlying single-process supervisor.
_BASE_CHECK = base.check_log_bytes
_BASE_FAULT = base.fault_log


def install(case, profile, ticket, slot, timeout):
    if slot != 2 or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError('invalid seat experiment configuration')
    protected = base.install(case, profile, ticket, slot)
    lab = case / 'extensions/x4_lan_lab'
    md, ui = lab / 'md', lab / 'ui'
    extra = [md / name for name in MD] + [ui / name for name in UI]
    for path in extra:
        shutil.copyfile(ROOT / 'tools/dev' / path.name, path)
    config = ui / 'config.lua'
    text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'):
        raise ValueError('unexpected private configuration')
    nonce = secrets.token_hex(16)
    config.write_text(text[:-2] + ',authority_player_seat_experiment=true,authority_player_seat_nonce="' + nonce +
                      '",authority_player_seat_timeout=' + format(timeout, '.17g') + '}\n', encoding='ascii')
    config.chmod(0o600)
    read = ui / 'authority_sector_read_probe.lua'
    with read.open('a', encoding='utf-8') as stream:
        stream.write('''\nfunction X4LAN_SECTOR_READ_EXPORT()
 if state~='done' or failed then error('read not complete') end
 guard()
 return first[4],first[5],first[2],sample.game
end
''')
    manifest = lab / 'ui.xml'
    text = manifest.read_text(encoding='utf-8')
    hook = '    <file name="ui/authority_download_load_probe.lua" />\n'
    if text.count(hook) != 1:
        raise ValueError('unexpected private manifest')
    manifest.write_text(text.replace(hook, ''.join('    <file name="ui/' + name + '" />\n' for name in UI) + hook), encoding='utf-8')
    owner = ui / 'authority_download_load_probe.lua'
    text = owner.read_text(encoding='utf-8')
    hook = " if state=='done' then return end\n"
    if text.count(hook) != 1:
        raise ValueError('unexpected update owner')
    owner.write_text(text.replace(hook, " if state=='done' then X4LAN_PLAYER_SEAT_EXPERIMENT_TICK();return end\n"), encoding='utf-8')
    if {p.name for p in md.iterdir()} != set((*base.MD, 'authority_sector_read_guard.xml', *MD)):
        raise ValueError('unexpected private MD scripts')
    return protected + extra


def fault(raw):
    lower = raw.lower()
    return (_BASE_FAULT(raw) or (TAG + 'ERROR').lower().encode() in lower or
            b'could not find suitable data type for conversion!' in lower or
            b'invalid data types for arithmetic operation!' in lower)


def validate(raw, ticket, slot, *, partial=False):
    if fault(raw):
        raise ValueError('seat experiment reported a fault')
    if not raw.endswith(b'\n') and partial:
        return None
    # Scan even an incomplete baseline: an experiment receipt before pause is
    # always an error, not a partial result to be silently retried.
    lines = raw.decode('utf-8').splitlines()
    pause_tag = base.load.TAG.decode() + 'pause_observed|'
    pauses = [i for i, line in enumerate(lines) if pause_tag in line]
    rows = [(i, line.split(TAG, 1)[1].strip()) for i, line in enumerate(lines) if TAG in line]
    if len(rows) > len(STEPS) or any(value != STEPS[i] for i, (_, value) in enumerate(rows)):
        raise ValueError('invalid, duplicate or reordered seat receipts')
    if rows and (len(pauses) != 1 or rows[0][0] <= pauses[0]):
        raise ValueError('seat experiment started before confirmed pause')
    observed = _BASE_CHECK(raw, ticket, slot, partial=partial)
    if observed is None:
        return None
    if observed['reported_pilot'] != 'present':
        raise ValueError('positive control NPC pilot missing from sector read')
    if len(rows) != len(STEPS):
        if partial:
            return None
        raise ValueError('missing seat experiment receipts')
    observed.update(diagnostic_completed=True, positive_control_observed=True,
                    two_negative_observations=True, seat_free_proven=False,
                    player_control_proven=False, save_authorized=False,
                    multiplayer_proven=False)
    return observed


def run(args):
    if args.slot != 2 or not math.isfinite(args.timeout) or args.timeout < 60:
        raise ValueError('seat experiment requires slot 2 and at least 60 seconds')
    out = base.snapshot.output_path(args.out)
    store = base.base.local_directory(args.store)
    source = store.parent
    if out.resolve().is_relative_to(source) or source.is_relative_to(out.resolve()):
        raise ValueError('output and checkpoint source must be separate')
    before = base.archive._path_fingerprints(store)
    old = (base.install, base.check_log_bytes, base.fault_log,
           base.base.readonly_save_command, base.result_finalizer)
    # The base supervisor is deliberately reused so the same owned process,
    # cancellation, lock and final-log validation rules apply. These temporary
    # changes make this entry point unsuitable for concurrent in-process runs.
    def install_private(case, profile, ticket, slot):
        # install() needs the original implementation while the supervisor needs
        # the wrapper. Avoid recursion without opening a cross-thread window.
        current = base.install
        try:
            base.install = old[0]
            return install(case, profile, ticket, slot, min(args.timeout, 120))
        finally:
            base.install = current
    def finalize(result):
        if base.archive._path_fingerprints(store) != before:
            raise ValueError('checkpoint source changed during experiment')
        result.update(scope='one isolated Linux X4; fixture creation and seat observation only',
                      checkpoint_requested=False, seat_free_proven=False,
                      player_control_proven=False, save_authorized=False,
                      multiplayer_proven=False)
    try:
        base.install = install_private
        base.check_log_bytes = validate
        base.fault_log = fault
        base.base.readonly_save_command = readonly.readonly_save_command
        base.result_finalizer = finalize
        return base.run(args)
    finally:
        (base.install, base.check_log_bytes, base.fault_log,
         base.base.readonly_save_command, base.result_finalizer) = old


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--store', type=Path, default=base.archive.DEFAULT_STORE)
    parser.add_argument('--display', required=True)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--seed', type=int, default=276944566)
    args = parser.parse_args()
    args.slot = 2
    try:
        result = run(args)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
