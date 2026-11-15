#!/usr/bin/env python3
"""Transfer an X4 checkpoint with two saved MD references to another live X4.

This opt-in disposable Linux diagnostic extends the two-X4 supervisor. The
server creates and names two fixture ships before its checkpoint; the second
process checks the restored MD references before producing its pause receipt.
No player is admitted and no gameplay is tested. Importing starts nothing.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_two_x4_live as base
import authority_identity_live as identity
from lockstep.launcher import extension


def inject(case, phase):
    lab = case/'extensions/x4_lan_lab'
    ui = lab/'ui'
    if phase not in ('save', 'load'):
        raise ValueError('invalid fixture phase')
    shutil.copyfile(ROOT/'tools/dev/authority_identity_fixture.xml', lab/'md/authority_identity_fixture.xml')
    shutil.copyfile(ROOT/'tools/dev/authority_identity_probe.lua', ui/'authority_identity_probe.lua')
    config = ui/'config.lua'
    text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'):
        raise ValueError('unexpected private configuration')
    config.write_text(text[:-2]+', authority_identity_phase="'+phase+'"}\n', encoding='ascii')
    if phase == 'save':
        probe = ui/'authority_world_bridge_probe.lua'
        old = ' if not started and now-loaded_at>=3 then\n'
        new = ' if not started and now-loaded_at>=3 and not X4LAN_IDENTITY_READY() then return end\n'+old
        files = [*extension.BASE_UI, 'ui/x4ls_autostart.lua', 'ui/authority_control_state.lua',
                 'ui/x4_control_engine.lua', 'ui/local_control_bridge.lua',
                 'ui/authority_identity_probe.lua', 'ui/authority_world_bridge_probe.lua']
    else:
        probe = ui/'authority_download_load_probe.lua'
        old = " elseif state=='observing' then\n"
        new = old+"  if not X4LAN_IDENTITY_READY() then return end\n"
        files = [*extension.BASE_UI, 'ui/client_load_barrier.lua', 'ui/x4_client_load_engine.lua',
                 'ui/authority_identity_probe.lua', 'ui/authority_download_load_probe.lua']
    text = probe.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise ValueError('unexpected harness probe')
    probe.write_text(text.replace(old, new), encoding='utf-8')
    (lab/'ui.xml').write_text(extension.ui_xml(files), encoding='utf-8')


def compare_observations(server_log, client_log):
    before = identity.observations(server_log, 'save')
    after = identity.observations(client_log, 'load')
    if [(x['name'], x['macro']) for x in before] != [(x['name'], x['macro']) for x in after]:
        raise ValueError('fixture references or properties differ between X4 processes')
    return {'fixture_count': 2, 'names_and_macros_match': True,
            'runtime_ids_equal': [a['id'] == b['id'] for a, b in zip(before, after)]}


def run(args):
    # Validate while the directory is still absent. The underlying supervisor
    # creates it, so calling output_path again after its return would reject it.
    out = base.snapshot.output_path(args.out)
    server_install = base.server.install_probe
    client_install = base.client.install_probe
    readonly_command = base.load.readonly_save_command
    def install_server(case, port, lease, epoch):
        server_install(case, port, lease, epoch)
        inject(case, 'save')
    def install_client(case, profile, ticket):
        config = client_install(case, profile, ticket)
        inject(case, 'load')
        return config
    def readonly_with_fixture(case, *args, **kwargs):
        command = readonly_command(case, *args, **kwargs)
        pos = command.index('--die-with-parent')
        lab = case/'extensions/x4_lan_lab'
        for path in (lab/'md/authority_identity_fixture.xml', lab/'ui/authority_identity_probe.lua'):
            command[pos:pos] = ['--ro-bind', str(path), str(path)]
            pos += 3
        return command
    try:
        base.server.install_probe = install_server
        base.client.install_probe = install_client
        base.load.readonly_save_command = readonly_with_fixture
        result = base.run(args)
        result['scope'] = ('two simultaneous isolated Linux X4 processes; local checkpoint transfer; '
                           'two fixture MD references; no admission or gameplay')
        if result.get('success'):
            profile = Path('case/home/.config/EgoSoft/X4/45841/engine-output.log')
            try:
                result.update(compare_observations(out/'server'/profile, out/'client'/profile))
                result['client_identity_before_pause_receipt'] = True
                result['exact_loaded_file_proven'] = False
            except (OSError, ValueError) as error:
                result.update(success=False, error=str(error))
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        return result
    finally:
        base.server.install_probe = server_install
        base.client.install_probe = client_install
        base.load.readonly_save_command = readonly_command


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--display', required=True)
    p.add_argument('--timeout', type=float, default=600)
    p.add_argument('--seed', type=int, default=276944566)
    try:
        result = run(p.parse_args())
    except (OSError, ValueError, RuntimeError) as error:
        p.exit(1, 'REFUSED: '+str(error)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1

if __name__ == '__main__':
    sys.exit(main())
