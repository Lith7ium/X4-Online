#!/usr/bin/env python3
"""Opt-in paused two-X4 saved-frame diagnostic; import never starts a game."""
import argparse
import json
import math
from pathlib import Path
import re
import secrets
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_census_pair_live as pair
import authority_census_archive_provenance as archive
import authority_sector_read_live as base
import authority_sector_pair_transfer_live as transfer
import authority_saved_frame_compare as evidence

BASE_MD=('authority_checkpoint_marker.xml','authority_ship_registry.xml','authority_identity_fixture.xml')
UI=('authority_checkpoint_marker_probe.lua','authority_registry_resolve_string.lua','authority_frame_read.lua')


def install(case,profile,ticket,config,nonce,timeout,window):
    if (config.get('role') not in ('server','client') or not re.fullmatch(r'[0-9a-f]{32}',nonce) or
        nonce==archive.REGISTRY_EPOCH or not math.isfinite(timeout) or not 60<=timeout<=600):
        raise ValueError('invalid paused frame configuration')
    config_path=base.load.install_probe(case,profile,ticket)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    md_names=BASE_MD+('authority_frame_read.xml',)
    for name in md_names:
        shutil.copyfile(archive.saved_state_script(name) if name in BASE_MD else ROOT/'tools/dev'/name,md/name)
    for name in UI:shutil.copyfile(ROOT/'tools/dev'/name,ui/name)
    marker=ui/'authority_checkpoint_marker_probe.lua'
    marker.write_text(transfer.once(marker.read_text(),"if phase~='load' or state~='inspect' or type(marker)~='string'",
        "if marker~=cfg.authority_expected_marker or phase~='load' or state~='inspect' or type(marker)~='string'"))
    text=config_path.read_text(encoding='ascii');literal=base.base.lua_literal
    if not text.endswith('}\n'):raise ValueError('unexpected private config')
    config_path.write_text(text[:-2]+(',authority_marker_phase="load",authority_expected_marker='+literal(archive.MARKER)+
        ',authority_frame_enabled=true,authority_frame_epoch='+literal(archive.REGISTRY_EPOCH)+
        ',authority_frame_nonce='+literal(nonce)+',authority_frame_ship_index='+str(evidence.SHIP_INDEX)+
        ',authority_frame_sector='+literal(evidence.SECTOR)+'}\n'),encoding='ascii');config_path.chmod(0o600)
    manifest=lab/'ui.xml';hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    manifest.write_text(transfer.once(manifest.read_text(),hook,''.join('    <file name="ui/'+n+'" />\n' for n in UI)+hook))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text()
    text=transfer.once(text,"local state='initial';local failed=false\n", "local state='initial';local failed=false\nlocal pause_requested=false;local pause_confirmed=false\n")
    text=transfer.once(text," elseif state=='observing' then\n", " elseif state=='observing' then\n"+'''  if not engine.is_paused() then
   if pause_confirmed then error('pre-test pause lost') end
   if not pause_requested then pause_requested=true;engine.pause() end
   return
  end
  pause_confirmed=true
  if not X4LAN_AUTHORITY_MARKER_READY() then return end
''')
    owner.write_text(transfer.once(text," if state=='done' then return end\n", " if state=='done' then X4LAN_FRAME_READ_TICK();return end\n"))
    if {p.name for p in md.iterdir()}!=set(md_names):raise ValueError('unexpected private MD scripts')
    return [config_path,lab/'ui.xml',lab/'content.xml',profile/'content.xml',profile/'config.xml']+[md/name for name in md_names]+[
        ui/name for name in (*UI,'sha256.lua','client_load_barrier.lua','x4_client_load_engine.lua','authority_download_load_probe.lua')]


class FrameCoordinator:
    def __init__(self,candidates):
        if evidence.SHIP_INDEX not in candidates.get(evidence.SECTOR,()):raise ValueError('selected saved ship lacks pinned witness')
        self.attempt=secrets.token_hex(16);self.roles={};self.launches={};self.identities={};self.results=None
        self.paths=tuple(ROOT/'tools/dev'/p for p in ('authority_frame_read.xml','authority_frame_read.lua',
                     'authority_saved_frame_compare.py','authority_saved_frame_pair_live.py'))
        self.fingerprints={p:base.stable_read(p,1<<20,collect=False)[:2] for p in self.paths}
    def check_sources(self):
        if any(base.stable_read(p,1<<20,collect=False)[:2]!=v for p,v in self.fingerprints.items()):
            raise ValueError('frame probe or coordinator changed')
    def add_role(self,role):
        if role not in ('server','client') or role in self.roles:raise ValueError('duplicate frame role')
        self.roles[role]={'snapshot':None};return {'role':role}
    def install(self,case,profile,ticket,config,nonce,timeout,window):
        role=config['role'];entry=self.roles[role]
        if ('nonce' in entry or nonce in (self.attempt,ticket['attempt_id']) or
            any(x.get('nonce')==nonce for x in self.roles.values())):raise ValueError('frame nonce reused')
        self.check_sources();entry.update(nonce=nonce,profile=profile,ticket=dict(ticket))
        result=install(case,profile,ticket,config,nonce,timeout,window);self.check_sources();return result
    def run(self,context):
        deadline=min(context['deadline']-5,time.monotonic()+110)
        if deadline-time.monotonic()<=10:raise TimeoutError('insufficient frame diagnostic time')
        while time.monotonic()<deadline:
            if context['check']() is not True:raise RuntimeError('frame lifecycle guard failed')
            identities={}
            for role,(proc,started,game) in self.launches.items():
                ident=base.load.game_identity(proc,started,game)
                if ident is None or (role in self.identities and self.identities[role]!=ident):
                    raise RuntimeError('frame X4 identity changed')
                identities[role]=ident
            if set(identities)!={'server','client'} or identities['server'][0]==identities['client'][0]:
                raise RuntimeError('frame requires distinct owned X4 processes')
            self.identities=identities
            self.check_sources();results={}
            for role,entry in self.roles.items():
                captured=base.read_live_log(entry['profile']/'engine-output.log',entry['snapshot'])
                if captured is None:continue
                raw,entry['snapshot']=captured
                if pair.load_observation(raw,entry['ticket'],partial=True) is None:continue
                pause=raw.find(base.load.TAG+b'pause_observed|');first=raw.find(evidence.TAG.encode('ascii'))
                if first>=0 and (pause<0 or first<pause):raise ValueError('frame read before observed pause')
                result=evidence.parse(raw,entry['nonce'],partial=True)
                if result is not None:results[role]=result
            if set(results)=={'server','client'}:
                self.results=evidence.compare(results['server'],results['client'])
                if context['check']() is not True:raise RuntimeError('frame lifecycle guard changed')
                self.check_sources();return self.results
            time.sleep(.2)
        raise TimeoutError('frame result deadline')
    def verify_final(self,logs):
        self.check_sources()
        results={r:evidence.parse(logs[r],entry['nonce']) for r,entry in self.roles.items()}
        return self.results is not None and evidence.compare(results['server'],results['client'])==self.results
    def cleanup_before_owned_processes(self):return True
    def cleanup_after_owned_processes(self):return True


def run(args):
    original=(pair.coordinator.CensusCoordinator,pair.installer.install,pair.load_observation,pair.owned.spawn_owned_gated)
    active=[None]
    def make(candidates):active[0]=FrameCoordinator(candidates);return active[0]
    def frame_install(case,profile,ticket,config,nonce,timeout,window):
        return active[0].install(case,profile,ticket,config,nonce,timeout,window)
    def load(raw,ticket,*,partial=False):
        lower=raw.lower()
        if b'[x4lan] auth_frame_read error ' in lower or b'maximum operator nesting level reached' in lower:
            raise ValueError('frame owner fault')
        return original[2](raw,ticket,partial=partial)
    def spawn(command,log,processes):
        result=original[3](command,log,processes);role=Path(log).parent.name
        if role not in ('server','client') or role in active[0].launches:raise ValueError('unexpected frame process role')
        active[0].launches[role]=(result[0],result[1],args.game.resolve(strict=True));return result
    try:
        pair.coordinator.CensusCoordinator=make;pair.installer.install=frame_install;pair.load_observation=load
        pair.owned.spawn_owned_gated=spawn
        result=pair.run(args)
        result.update(scope='two isolated paused Linux X4; saved local frame anchor comparison only',
                      checkpoint_identity_proven=False,actor_identity_proven=False,
                      universal_frame_identity_proven=False,ship_creation_requested=False,multiplayer_proven=False)
        (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        return result
    finally:
        (pair.coordinator.CensusCoordinator,pair.installer.install,pair.load_observation,pair.owned.spawn_owned_gated)=original


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--timeout',type=float,default=300);p.add_argument('--window',type=float,default=60)
    p.add_argument('--seed',type=int,default=276944566)
    try:result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error:p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1
if __name__=='__main__':sys.exit(main())
