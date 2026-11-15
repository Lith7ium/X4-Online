#!/usr/bin/env python3
"""Opt-in two-X4 existing-ship sector-reference diagnostic; never starts on import."""
import argparse
import json
from pathlib import Path
import re
import secrets
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_two_x4_live as base
import authority_checkpoint_marker_live as marker
import authority_sector_reference_evidence as evidence
from authority.checkpoints import CheckpointStore
from authority.marker_evidence import verify_saved_marker

FILES=(('tools/dev/authority_checkpoint_marker.xml','md/authority_checkpoint_marker.xml'),
       ('tools/dev/authority_ship_registry.xml','md/authority_ship_registry.xml'),
       ('tools/dev/authority_sector_reference_fixture.xml','md/authority_sector_reference_fixture.xml'),
       ('tools/dev/authority_checkpoint_marker_probe.lua','ui/authority_checkpoint_marker_probe.lua'),
       ('src/authority/lua/x4_ship_engine.lua','ui/x4_ship_engine.lua'),
       ('tools/dev/authority_sector_reference_probe.lua','ui/authority_sector_reference_probe.lua'))


def inject(case,phase,marker_value,epoch):
    if phase not in ('save','load') or not re.fullmatch(r'[0-9a-f]{32}',marker_value) or not re.fullmatch(r'[0-9a-f]{32}',epoch):
        raise ValueError('invalid sector fixture config')
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui'
    for source,target in FILES: shutil.copyfile(ROOT/source,lab/target)
    config=ui/'config.lua';text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected sector config')
    suffix=', authority_marker_phase="'+phase+'", authority_sector_phase="'+phase+'", authority_sector_epoch="'+epoch+'", authority_sector_deadline=120'
    if phase=='save': suffix+=', authority_marker="'+marker_value+'"'
    config.write_text(text[:-2]+suffix+'}\n',encoding='ascii')
    probe=ui/('authority_world_bridge_probe.lua' if phase=='save' else 'authority_download_load_probe.lua')
    text=probe.read_text(encoding='utf-8')
    if phase=='save':
        hook=' if not started and now-loaded_at>=3 then\n'
        replacement=(' if not started and now-loaded_at>=3 and not X4LAN_AUTHORITY_MARKER_READY() then return end\n'
                     ' if not started and now-loaded_at>=3 and not X4LAN_AUTHORITY_SECTOR_READY() then return end\n'+hook)
    else:
        hook=" elseif state=='observing' then\n"
        replacement=(hook+'  if not X4LAN_AUTHORITY_MARKER_READY() then return end\n'
                     '  if not X4LAN_AUTHORITY_SECTOR_READY() then return end\n')
    if text.count(hook)!=1: raise ValueError('unexpected bridge hook')
    text=text.replace(hook,replacement)
    if phase=='save':
        update=' local ok,reason=bridge:update();assert(ok,reason)\n'
        if text.count(update)!=1: raise ValueError('unexpected bridge update')
        text=text.replace(update,' X4LAN_AUTHORITY_SECTOR_ENSURE_PAUSED()\n'+update)
    probe.write_text(text,encoding='utf-8')
    manifest=lab/'ui.xml';text=manifest.read_text(encoding='utf-8')
    hook='    <file name="ui/'+probe.name+'" />\n'
    if text.count(hook)!=1: raise ValueError('unexpected bridge manifest')
    additions=''.join('    <file name="'+name+'" />\n' for name in (
        'ui/authority_checkpoint_marker_probe.lua','ui/x4_ship_engine.lua','ui/authority_sector_reference_probe.lua'))
    manifest.write_text(text.replace(hook,additions+hook),encoding='utf-8')


def observations(path,phase,epoch):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>256<<20: raise ValueError('sector log missing or oversized')
    tag='[X4LAN] AUTH_SECTOR '+phase+' '
    rows=[line.split(tag,1)[1].strip() for line in path.read_text(encoding='utf-8',errors='strict').splitlines() if tag in line]
    if rows != ['VERIFIED '+epoch+' slots=2']: raise ValueError('sector receipt missing, duplicated, or failed')


def run(args):
    out=base.snapshot.output_path(args.out)
    marker_value=secrets.token_hex(16);epoch=secrets.token_hex(16);tickets=[]
    old_server,old_client=base.server.install_probe,base.client.install_probe
    old_readonly,old_transfer=base.load.readonly_save_command,base.offer_and_download
    def install_server(case,port,lease,world_epoch):
        old_server(case,port,lease,world_epoch);inject(case,'save',marker_value,epoch)
    def install_client(case,profile,ticket):
        config=old_client(case,profile,ticket);inject(case,'load',marker_value,epoch);return config
    def readonly(case,*a,**kw):
        command=old_readonly(case,*a,**kw);pos=command.index('--die-with-parent');lab=case/'extensions/x4_lan_lab'
        for _,relative in FILES:
            path=lab/relative;command[pos:pos]=['--ro-bind',str(path),str(path)];pos+=3
        return command
    def transfer(*a,**kw):
        ticket,target=old_transfer(*a,**kw);tickets.append(dict(ticket));return ticket,target
    try:
        base.server.install_probe=install_server;base.client.install_probe=install_client
        base.load.readonly_save_command=readonly;base.offer_and_download=transfer
        result=base.run(args)
    finally:
        base.server.install_probe=old_server;base.client.install_probe=old_client
        base.load.readonly_save_command=old_readonly;base.offer_and_download=old_transfer
    result['scope']='two isolated Linux X4 processes, two existing ships, checkpoint transfer; no admission or gameplay'
    result.update(runtime_binding_proven=False,exact_loaded_file_proven=False,universe_coverage_proven=False)
    if result.get('success'):
        try:
            if len(tickets)!=1: raise ValueError('expected one load offer')
            log=Path('case/home/.config/EgoSoft/X4/45841/engine-output.log')
            server=out/'server'/log;client=out/'client'/log
            observations(server,'save',epoch);observations(client,'load',epoch)
            marker.verify_receipts(server.read_text(),client.read_text(),marker_value,tickets[0])
            checkpoint=CheckpointStore(out/'checkpoints').latest_confirmed()
            if checkpoint.checkpoint_id!=tickets[0]['checkpoint_id'] or checkpoint.sha256!=tickets[0]['sha256']:
                raise ValueError('confirmed checkpoint differs from offered save')
            verify_saved_marker(checkpoint,marker_value,script_name='X4AuthorityCheckpointMarker',cue_name='Store')
            result.update(evidence.verify(checkpoint,epoch))
            result['marker_restored_after_game_loaded']=True
            result['fixture_verified_in_both_paused_processes']=True
        except (OSError,ValueError,RuntimeError) as error:
            result.update(success=False,error=str(error))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--display',required=True);p.add_argument('--timeout',type=float,default=600)
    p.add_argument('--seed',type=int,default=276944566)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1


if __name__=='__main__': sys.exit(main())
