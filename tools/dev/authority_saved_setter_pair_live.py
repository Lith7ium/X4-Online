#!/usr/bin/env python3
"""One-shot isolated saved-actor setter diagnostic; import starts nothing.

Uses actual source sample; no obstacle-clearance or general frame claim. A
failure after dispatch may follow an irreversible write to the private case.
"""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_source_motion_pair_live as motion
import authority_census_replica_live as lifecycle
import authority_census_archive_provenance as archive
import authority_saved_frame_compare as frame
import authority_sector_pair_transfer_live as transfer
from authority.experimental_tcp_motion import motion_digest

APPLY_TAG='[X4LAN] AUTH_MOTION_APPLY '


def verify_apply(raw,sample):
    """Correlate the one before/write/readback series to the sent sample."""
    if type(raw) is not bytes or not raw.endswith(b'\n'):raise ValueError('incomplete setter log')
    lines=raw.decode('utf-8').splitlines();rows=[];buffered=False
    for line in lines:
        if '[X4LAN] AUTH_PARTICIPANT_MOTION BUFFERED ' in line:buffered=True
        if APPLY_TAG in line:
            if not buffered:raise ValueError('setter before buffer')
            rows.append(line.split(APPLY_TAG,1)[1].strip().split())
    if len(rows)!=3 or [r[0] for r in rows]!=['INTENT','WRITE_ENTERED','READBACK']:
        raise ValueError('one setter attempt and readback required')
    a,b,c=rows
    if len(a)!=12 or len(b)!=2 or len(c)!=10 or not re.fullmatch(r'[0-9a-f]{32}',a[1]) or b[1]!=a[1] or c[1]!=a[1]:
        raise ValueError('setter operation identity differs')
    digest=motion_digest(sample);identity=[str(sample['index']),str(sample['sequence']),digest]
    if a[2:5]!=identity or c[2:5]!=identity:raise ValueError('setter sample identity differs')
    try:before=list(map(float,a[5:8]));target=list(map(float,a[8:11]));game_before=float(a[11]);after=list(map(float,c[5:8]));game_after=float(c[8]);elapsed=float(c[9])
    except ValueError:raise ValueError('invalid setter evidence number') from None
    if not all(math.isfinite(x) for x in before+target+after+[game_before,game_after,elapsed]):raise ValueError('nonfinite setter evidence')
    expected=[sample[k] for k in ('x','y','z')]
    if target!=expected or not 5<=math.dist(before,target)<=50 or math.dist(after,target)>3 or game_after<=game_before or elapsed<1:
        raise ValueError('setter readback differs from guarded experiment')
    return {'index':sample['index'],'sequence':sample['sequence'],'sample_sha256':digest,'before':before,
            'target':target,'readback':after,'source_time':sample['source_time'],'client_game_before':game_before,
            'client_game_after':game_after,'readback_elapsed':elapsed,'target_distance_before':math.dist(before,target),
            'target_distance_after':math.dist(after,target)}


class SetterCoordinator(motion.MotionCoordinator):
    @staticmethod
    def _sources():
        return tuple(sorted(set(motion.MotionCoordinator._sources())|{ROOT/'tools/dev'/p for p in (
            'authority_saved_setter_pair_live.py','authority_saved_frame_compare.py','authority_frame_read.lua',
            'authority_frame_read.xml','authority_saved_motion_apply.xml')}|{ROOT/'src/authority/lua/saved_motion_apply.lua'}))
    def __init__(self,candidates,*,defer_source_ack=False):
        super().__init__(candidates,defer_source_ack=defer_source_ack,motion_count=1,saved_index=frame.SHIP_INDEX)
        if self.saved_sector!=frame.SECTOR:raise ValueError('saved sector differs from frame experiment')
        self.frame_records=None;self.profiles={};self.frame_nonces={};self.frame_snapshots={};self.apply_possible=False
    def motion_settings(self,settings):return dict(settings,saved_apply=True)
    def worker_config(self,config):return dict(config,apply_once=True)
    def install(self,case,profile,ticket,config,nonce,timeout,window):
        files=super().install(case,profile,ticket,config,nonce,timeout,window)
        role=config['role'];self.profiles[role]=profile;fn=self.fresh();self.frame_nonces[role]=fn
        lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
        for name in ('authority_frame_read.lua',):shutil.copyfile(ROOT/'tools/dev'/name,ui/name)
        shutil.copyfile(ROOT/'tools/dev/authority_frame_read.xml',md/'authority_frame_read.xml')
        manifest=lab/'ui.xml';hook='    <file name="ui/authority_download_load_probe.lua" />\n'
        manifest.write_text(transfer.once(manifest.read_text(),hook,'    <file name="ui/authority_frame_read.lua" />\n'+hook))
        cp=ui/'config.lua';text=cp.read_text(encoding='ascii');literal=lifecycle.base.base.lua_literal
        if not text.endswith('}\n'):raise ValueError('unexpected private config')
        text=text[:-2]+(',authority_frame_enabled=true,authority_frame_epoch='+literal(archive.REGISTRY_EPOCH)+
            ',authority_frame_nonce='+literal(fn)+',authority_frame_ship_index=1318,authority_frame_sector='+literal(frame.SECTOR)+'}\n')
        cp.write_text(text,encoding='ascii');cp.chmod(0o600)
        owner=ui/'authority_download_load_probe.lua';text=owner.read_text()
        old=" if state=='done' then X4LAN_"+('SOURCE_SINGLE_JOB' if role=='server' else 'PARTICIPANT_JOB')+"_TICK();return end\n"
        new=(" if state=='done' then\n  if not frame_handoff then\n   X4LAN_FRAME_READ_TICK()\n"
             "   if X4LAN_FRAME_READ_DONE() then frame_handoff=true else return end\n  end\n  X4LAN_"+
             ('SOURCE_SINGLE_JOB' if role=='server' else 'PARTICIPANT_JOB')+"_TICK();return\n end\n")
        text=transfer.once(text,"local state='initial';local failed=false\n", "local state='initial';local failed=false\nlocal frame_handoff=false\n")
        owner.write_text(transfer.once(text,old,new));self.check_sources()
        return files+[ui/'authority_frame_read.lua',md/'authority_frame_read.xml']
    def await_frame(self,context):
        deadline=min(context['deadline']-55,time.monotonic()+90)
        while time.monotonic()<deadline:
            if context['check']() is not True:raise RuntimeError('frame lifecycle guard failed')
            self.check_sources();rows={}
            for role in ('server','client'):
                captured=lifecycle.base.read_live_log(self.profiles[role]/'engine-output.log',self.frame_snapshots.get(role))
                if captured is None:continue
                raw,self.frame_snapshots[role]=captured
                if lifecycle.load_observation(raw,self.tickets[role],partial=True) is None:continue
                pause=raw.find(lifecycle.base.load.TAG+b'pause_observed|');first=raw.find(frame.TAG.encode())
                if first>=0 and (pause<0 or first<pause):raise ValueError('frame read before observed pause')
                row=frame.parse(raw,self.frame_nonces[role],partial=True)
                if row is not None:rows[role]=row
            if set(rows)=={'server','client'}:
                self.frame_records=frame.compare(rows['server'],rows['client'])
                if context['check']() is not True:raise RuntimeError('frame guard changed')
                self.check_sources();return
            time.sleep(.2)
        raise TimeoutError('paused frame comparison incomplete')
    def _validate_motion_result(self,result):
        if type(result) is not dict or result.get('motion_pose_applied') is not True:raise ValueError('setter receipt missing')
        copy=dict(result,motion_pose_applied=False);super()._validate_motion_result(copy)
    def run(self,context):
        self.await_frame(context);self.apply_possible=True
        # Keep the legacy lifecycle's preliminary read-only flag until the
        # independent final client log has confirmed the readback as well.
        details=super().run(context);details.update(frame_comparison=self.frame_records,
                                                   frame_identity_proven=False,clearance_proven=False)
        return details
    def verify_final(self,logs):
        super().verify_final(logs)
        rows={role:frame.parse(logs[role],self.frame_nonces[role]) for role in ('server','client')}
        if frame.compare(rows['server'],rows['client'])!=self.frame_records:raise ValueError('frame result changed')
        report=verify_apply(logs['client'],self.result['motion_sample'])
        self.output_details['setter_readback']=report
        self.output_details['motion_pose_applied']=True
        return True


def run(args):
    args.defer_source_ack=True;args.two_clients=False;active=[None]
    original=(lifecycle.coordinator.CensusCoordinator,lifecycle.installer.install,lifecycle.owned.spawn_owned_gated,lifecycle.load_observation)
    def make(candidates,*,defer_source_ack=False):active[0]=SetterCoordinator(candidates,defer_source_ack=defer_source_ack);return active[0]
    def install(case,profile,ticket,config,nonce,timeout,window):return active[0].install(case,profile,ticket,config,nonce,timeout,window)
    def spawn(command,log,processes):
        result=original[2](command,log,processes);role=Path(log).parent.name
        if role not in ('server','client') or role in active[0].launches:raise ValueError('unexpected owned role')
        active[0].launches[role]=(result[0],result[1],args.game.resolve(strict=True));return result
    def load(raw,ticket,*,partial=False):
        if motion.pair.private_fault(raw) or b'[x4lan] auth_frame_read error ' in raw.lower() or b'[x4lan] auth_motion_apply error ' in raw.lower():
            raise ValueError('frame or setter owner fault')
        return original[3](raw,ticket,partial=partial)
    try:
        lifecycle.coordinator.CensusCoordinator=make;lifecycle.installer.install=install
        lifecycle.owned.spawn_owned_gated=spawn;lifecycle.load_observation=load
        result=lifecycle.run(args)
        result.update(scope='isolated saved actor: paused frame anchors then one source-sample setter readback',
            checkpoint_identity_proven=False,frame_identity_proven=False,clearance_proven=False,multiplayer_proven=False)
        if not result.get('success'):
            result['setter_outcome_uncertain']=bool(active[0] and active[0].apply_possible)
            result['motion_pose_applied']=None
            if type(result.get('participant')) is dict:
                result['participant']['motion_pose_applied']=None
        (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        return result
    finally:
        (lifecycle.coordinator.CensusCoordinator,lifecycle.installer.install,lifecycle.owned.spawn_owned_gated,lifecycle.load_observation)=original


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--timeout',type=float,default=300);p.add_argument('--window',type=float,default=60)
    p.add_argument('--seed',type=int,default=276944566)
    try:r=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as e:p.exit(1,'REFUSED: '+str(e)+'\n')
    print(json.dumps(r,indent=2));return 0 if r['success'] else 1
if __name__=='__main__':sys.exit(main())
