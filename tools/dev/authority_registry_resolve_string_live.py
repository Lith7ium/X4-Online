#!/usr/bin/env python3
"""Opt-in single-X4 string Resolve experiment; import starts no process."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_registry_resolve_v2_live as base


def install(case,profile,*,port,lease,epoch,id1,id2):
    if any(not base.HEX.fullmatch(x) for x in (lease,epoch,id1,id2)) or len({lease,epoch,id1,id2})!=4:
        raise ValueError('invalid isolated probe tokens')
    base_install=base.world_bridge.install_probe
    # Build the same disposable sandbox without installing the table cue.
    base_install(case,port,lease,epoch)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui'
    for name in ('authority_ship_registry.xml','authority_registry_resolve_string.xml'):
        shutil.copyfile(ROOT/'tools/dev'/name,lab/'md'/name)
    for source,target in ((ROOT/'src/authority/lua/x4_ship_engine.lua','x4_ship_engine.lua'),
                          (ROOT/'tools/dev/authority_registry_resolve_string.lua','authority_registry_resolve_string.lua'),
                          (ROOT/'tools/dev/authority_registry_resolve_string_native.lua','authority_registry_resolve_string_native.lua')):
        shutil.copyfile(source,ui/target)
    cfg=ui/'config.lua';text=cfg.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected probe config')
    suffix=(f', authority_resolve_string_native=true, authority_resolve_epoch="{epoch}",'
            f' authority_resolve_id1="{id1}", authority_resolve_id2="{id2}",'
            f' authority_resolve_save_path={json.dumps(str(profile/"save"))}')
    cfg.write_text(text[:-2]+suffix+'}\n',encoding='ascii');cfg.chmod(0o600)
    manifest=lab/'ui.xml';text=manifest.read_text(encoding='utf-8')
    hook='    <file name="ui/authority_world_bridge_probe.lua" />\n'
    if text.count(hook)!=1: raise ValueError('missing manifest hook')
    added=''.join(f'    <file name="ui/{name}" />\n' for name in ('x4_ship_engine.lua',
        'authority_registry_resolve_string.lua','authority_registry_resolve_string_native.lua'))
    manifest.write_text(text.replace(hook,added+hook),encoding='utf-8')
    bridge=ui/'authority_world_bridge_probe.lua';text=bridge.read_text(encoding='utf-8')
    hook=' if not started and now-loaded_at>=3 then\n'
    if text.count(hook)!=1: raise ValueError('missing bridge hook')
    bridge.write_text(text.replace(hook,' if not started and now-loaded_at>=3 and not X4LAN_RESOLVE_STRING_NATIVE_READY() then return end\n'+hook),encoding='utf-8')


def check_log(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>32<<20: raise ValueError('invalid probe log')
    tag='[X4LAN] AUTH_RESOLVE_STRING '
    rows=[line.split(tag,1)[1].strip() for line in path.read_text(encoding='utf-8',errors='strict').splitlines() if tag in line]
    if (len(rows)!=5 or not rows[0].startswith('SHAPE stage=ok type=string actor_format=hex ')
            or rows[1]!='ACTOR_MATCH' or not rows[2].startswith('SHAPE stage=unavailable type=string actor_format=hex ')
            or rows[3:]!=['UNAVAILABLE','DONE']):
        raise ValueError('missing, duplicate or reordered native receipts')
    return {'actor_match_observed':True,'correlated_unavailable_observed':True,'shape_rows':[rows[0],rows[2]]}


def probe_fault(path):
    if not path.exists(): return False
    if path.is_symlink() or not path.is_file() or path.stat().st_size>32<<20: raise ValueError('invalid probe log')
    with path.open('rb') as stream:
        stream.seek(max(0,path.stat().st_size-(1<<16)))
        return b'[X4LAN] AUTH_RESOLVE_STRING ERROR ' in stream.read(1<<16)


def run(args):
    old_install,old_check,old_fault=base.install,base.check_log,base.probe_fault
    try:
        base.install,base.check_log,base.probe_fault=install,check_log,probe_fault
        result=base.run(args)
    finally:
        base.install,base.check_log,base.probe_fault=old_install,old_check,old_fault
    result['scope']='one isolated Linux X4; local string/actor diagnostic; no multiplayer'
    if 'error' in result: result['error']=result['error'].replace('ResolveV2','ResolveString')
    (args.out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--display',required=True);p.add_argument('--timeout',type=float,default=120)
    p.add_argument('--seed',type=int,default=276944566)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1


if __name__=='__main__': sys.exit(main())
