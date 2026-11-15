#!/usr/bin/env python3
"""Disposable two-process MD reference persistence experiment; no multiplayer.

Runs the established private save harness, ends its process, and starts the
established private read-only load harness. Never executes merely on import.
A passing result covers only these two created, named fixture ships.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_control_live as control
import authority_load_live as load
from lockstep.launcher import extension
import linux_snapshot_capture as snapshot


def inject(case, phase):
    lab=case/'extensions/x4_lan_lab'; ui=lab/'ui'
    shutil.copyfile(ROOT/'tools/dev/authority_identity_fixture.xml',lab/'md/authority_identity_fixture.xml')
    shutil.copyfile(ROOT/'tools/dev/authority_identity_probe.lua',ui/'authority_identity_probe.lua')
    config=ui/'config.lua'
    text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'):
        raise ValueError('unexpected private configuration')
    config.write_text(text[:-2]+', authority_identity_phase="'+phase+'"}\n',encoding='ascii')
    if phase=='save':
        probe=ui/'authority_control_probe.lua'
        text=probe.read_text(encoding='utf-8')
        old='  initialize()\n'
        new='  if not X4LAN_IDENTITY_READY() then return end\n  initialize()\n'
        files=[*extension.BASE_UI,'ui/x4ls_autostart.lua','ui/control_state.lua',
               'ui/x4_control_engine.lua','ui/authority_identity_probe.lua','ui/authority_control_probe.lua']
    elif phase=='load':
        probe=ui/'authority_load_probe.lua'
        text=probe.read_text(encoding='utf-8')
        old="   state='done';log(('ADVANCED time=%.17g'):format(current))\n"
        new="   if not X4LAN_IDENTITY_READY() then return end\n"+old
        files=[*extension.BASE_UI,'ui/authority_identity_probe.lua','ui/authority_load_probe.lua']
    else: raise ValueError('invalid phase')
    if text.count(old)!=1: raise ValueError('unexpected harness probe')
    probe.write_text(text.replace(old,new),encoding='utf-8')
    (lab/'ui.xml').write_text(extension.ui_xml(files),encoding='utf-8')


def observations(path,phase):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 << 20:
        raise ValueError('identity log unavailable or too large')
    raw=path.read_bytes()
    return observations_bytes(raw,phase)


def observations_bytes(raw,phase):
    """Parse already captured identity-log bytes; caller owns snapshot stability."""
    if type(raw) is not bytes or len(raw) > 256 << 20 or phase not in ('save','load'):
        raise ValueError('invalid identity observation bytes')
    tag=b'[X4LAN] AUTH_IDENTITY '+phase.encode('ascii')+b' '
    rows=[line.split(tag,1)[1].strip() for line in raw.splitlines() if tag in line]
    pattern=rb'ACTOR ([12]) id=([0-9]+) name=(Authority identity (?:alpha 7181|beta 7182)) macro=(ship_arg_s_fighter_01_a_macro)'
    if len(rows)!=3 or rows[-1]!=b'READY': raise ValueError('incomplete identity observations')
    parsed=[]
    for index,row in enumerate(rows[:2],1):
        match=re.fullmatch(pattern,row)
        if not match or int(match.group(1))!=index or int(match.group(2))==0:
            raise ValueError('invalid identity observation')
        parsed.append({'id':match.group(2).decode('ascii'),'name':match.group(3).decode('ascii'),
                       'macro':match.group(4).decode('ascii')})
    if parsed[0]['id']==parsed[1]['id'] or parsed[0]['name']==parsed[1]['name']:
        raise ValueError('fixture objects not distinguishable')
    return parsed


def run(args):
    out=snapshot.output_path(args.out)
    out.mkdir(parents=True,mode=0o700,exist_ok=False)
    result={'success':False,'scope':'two fixture ships in disposable Linux X4; no multiplayer',
            'cross_process_runtime_id_stability_claimed':False}
    orig_control=control.install_probe;orig_load=load.install_probe
    try:
        def save_install(case,port,lease):
            orig_control(case,port,lease);inject(case,'save')
        control.install_probe=save_install
        save=control.run(SimpleNamespace(game=args.game,out=out/'save',display=args.display,
                                       timeout=args.timeout,seed=args.seed))
        if not save.get('success'): raise RuntimeError('save harness failed: '+save.get('error','unknown'))
        before=observations(out/'save/case/home/.config/EgoSoft/X4/45841/engine-output.log','save')
        def load_install(case,profile):
            orig_load(case,profile);inject(case,'load')
        load.install_probe=load_install
        restored=load.run(SimpleNamespace(game=args.game,out=out/'load',display=args.display,
                           timeout=args.timeout,seed=args.seed,store=out/'save/checkpoints',
                           checkpoint_id=save['checkpoint_id']))
        if not restored.get('success'): raise RuntimeError('load harness failed: '+restored.get('error','unknown'))
        after=observations(out/'load/case/home/.config/EgoSoft/X4/45841/engine-output.log','load')
        if [(x['name'],x['macro']) for x in before] != [(x['name'],x['macro']) for x in after]:
            raise RuntimeError('saved fixture references or properties differ after load')
        result.update(success=True,save_process_cleaned=save.get('owned_processes_remaining')==[],
                      load_process_cleaned=restored.get('owned_processes_remaining')==[],
                      names_and_macros_match=True,fixture_count=2,
                      runtime_ids_equal=[a['id']==b['id'] for a,b in zip(before,after)],
                      read_only_load=restored.get('read_only_staged_save') is True)
    except (Exception,KeyboardInterrupt) as error:
        result['error']=str(error)
    finally:
        control.install_probe=orig_control;load.install_probe=orig_load
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',required=True,type=Path);parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--display',required=True);parser.add_argument('--timeout',type=float,default=600)
    parser.add_argument('--seed',type=int,default=276944566)
    try: result=run(parser.parse_args())
    except (OSError,ValueError,RuntimeError) as error: parser.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__': sys.exit(main())
