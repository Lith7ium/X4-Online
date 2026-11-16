#!/usr/bin/env python3
"""Opt-in disposable client-to-server one-shot diagnostic; import starts nothing.

Admission and the authority grant are synthetic. No clearance, persistent
world, HA handover, or general frame equivalence is asserted.
"""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_client_authority_pair_live as base
import authority_client_authority_saved_frame_install as install
import authority_census_replica_live as lifecycle
import authority_census_archive_provenance as archive
import authority_saved_frame_compare as frame
import authority_saved_setter_pair_live as setter
import authority_source_tcp_pair_live as pair
import authority_source_motion_pair_live as motion_pair
import authority_client_to_server_apply_worker as worker
from authority_helper_lifecycle import OwnedHelper
from authority_tcp_native_worker import parse_json

class Coordinator(base.ClientAuthorityCoordinator):
    @staticmethod
    def _sources():
        paths=set(base.ClientAuthorityCoordinator._sources())|set(setter.SetterCoordinator._sources())
        paths.update(ROOT/'tools/dev'/n for n in ('authority_client_to_server_apply_pair_live.py',
            'authority_client_to_server_apply_worker.py','authority_client_authority_saved_frame_install.py'))
        return tuple(sorted(paths))
    def __init__(self,candidates,*,defer_source_ack=False):
        super().__init__(candidates,defer_source_ack=defer_source_ack,sample_count=2)
        self.profiles={};self.frame_nonces={};self.frame_snapshots={};self.frame_records=None
        self.apply_possible=False;self.server_snapshot=None
    def add_role(self,role):
        result=super().add_role(role)
        if role=='server':
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            try:
                sock.bind(('127.0.0.1',0));self.roles[role].update(motion=sock,motion_lease=self.fresh(),
                    motion_attempt=self.fresh(),motion_nonce=self.fresh())
            except BaseException:sock.close();raise
        return result
    def install(self,case,profile,ticket,config,nonce,timeout,window):
        role=config.get('role');self.profiles[role]=Path(profile);fn=self.fresh();self.frame_nonces[role]=fn
        if role=='client':
            files=super().install(case,profile,ticket,config,nonce,timeout,window)
            files+=install.add_frame(case,nonce=fn,forbidden=list(self._used-{fn}),enabled=True)
        elif role=='server':
            self.check_sources()
            if role not in self.roles or role in self.tickets or ticket['world_epoch']!=self.attempt:raise ValueError('private ticket differs')
            self.tickets[role]=dict(ticket);r=self.roles[role]
            settings={'participant_port':r['control'].getsockname()[1],'participant_lease':r['control_lease'],
                'job_port':r['job'].getsockname()[1],'lease':r['lease'],'attempt':r['attempt'],
                'epoch':archive.REGISTRY_EPOCH,'generation':self.generation,'nonce':r['nonce'],'seed':7183,'timeout':25}
            m={'port':r['motion'].getsockname()[1],'lease':r['motion_lease'],'attempt':r['motion_attempt'],
               'epoch':archive.REGISTRY_EPOCH,'generation':self.generation,'nonce':r['motion_nonce'],
               'timeout':15,'max_age':15,'max_tracks':1024,'saved_baseline':True,'saved_apply':True,'immediate_readback':True}
            files=install.install_server(case,profile,ticket,settings,self.witnesses,m,frame_nonce=fn,enabled=True)
        else:raise ValueError('unknown role')
        self.check_sources();return files
    def await_frame(self,context):
        setter.SetterCoordinator.await_frame(self,context)
        if context['check']() is not True:raise RuntimeError('frame lifecycle changed')
        rows={}
        for role in ('server','client'):
            _,_,raw=lifecycle.base.stable_read(self.profiles[role]/'engine-output.log',32<<20,collect=True)
            rows[role]=frame.parse(raw,self.frame_nonces[role])
        if frame.compare(rows['server'],rows['client'])!=self.frame_records:raise ValueError('frame comparison changed')
        ship=rows['server']['ship']
        self.server_snapshot=worker.snapshot_value({'role':'server','nonce':self.frame_nonces['server'],
            'epoch':archive.REGISTRY_EPOCH,'index':base.INDEX,'code':ship['code'],'macro':ship['macro'],
            'faction':ship['faction'],'sector_macro':ship['sector'],'game_time':ship['game'],
            'position':list(ship['position'])},archive.REGISTRY_EPOCH)
        if context['check']() is not True:raise RuntimeError('frame lifecycle changed')
        self.check_sources()
    def run(self,context):
        self.await_frame(context)
        deadline=min(context['deadline']-5,time.monotonic()+110)
        if deadline-time.monotonic()<=40:raise TimeoutError('insufficient pair time')
        def guard():
            if context['check']() is not True or time.monotonic()>=deadline:raise RuntimeError('pair context changed')
            self.check_sources()
            if time.monotonic()>=deadline:raise TimeoutError('source check timed out')
            return True
        def identity(role):
            proc,started,game=self.launches[role];ident=lifecycle.base.load.game_identity(proc,started,game)
            if ident is None:raise RuntimeError('owned X4 unavailable')
            st=os.stat('/proc/'+str(ident[0])+'/exe')
            return {'pid':ident[0],'start_ticks':ident[1],'exe_dev':st.st_dev,'exe_ino':st.st_ino}
        guard();server=identity('server');client=identity('client');guard()
        if server['pid']==client['pid']:raise RuntimeError('X4 roles share PID')
        self.private,self.child=socket.socketpair();r=self.roles['client'];s=self.roles['server']
        sockets=(r['control'],r['job'],r['authority'],s['control'],s['job'],s['motion'],self.child)
        fds=tuple(x.fileno() for x in sockets)
        helper=OwnedHelper([sys.executable,str(ROOT/'tools/dev/authority_client_to_server_apply_worker.py'),*(str(x) for x in fds)],registry=self.helpers,pass_fds=fds)
        for sock in sockets:sock.close()
        cfg=self.worker_config(r,server,client,deadline)
        cfg.update(server_participant_lease=s['control_lease'],server_job_lease=s['lease'],server_job_attempt=s['attempt'],
                   server_motion_lease=s['motion_lease'],server_motion_attempt=s['motion_attempt'],server_snapshot=self.server_snapshot)
        payload=json.dumps(cfg,separators=(',',':'),allow_nan=False).encode('ascii')+b'\n'
        if len(payload)>16384:raise ValueError('worker config too large')
        self.private.settimeout(min(2,deadline-time.monotonic()));self.private.sendall(payload);guard()
        self.apply_possible=True;helper.release();guard()
        reader=pair.ProgressFrames(self.private);result=parse_json(reader.read(deadline,guard));guard();self.validate_result(result)
        if helper.proc.wait(timeout=min(5,max(.01,deadline-time.monotonic())))!=0:raise RuntimeError('worker failed')
        motion_pair.finish_worker_output(self.private,reader,deadline,guard);guard();self.result=result
        details={'client_authority_registered':True,'client_authority_index':base.INDEX,'client_authority_sample_received':True,
            'server_x4_motion_applied':True,'server_apply_receipt':True,'checkpoint_identity_proven':False,
            'frame_identity_proven':False,'clearance_proven':False,'synthetic_tcp_checkpoint_and_admission':True,
            'samples':result['samples'],'frame_comparison':self.frame_records,'server_snapshot':self.server_snapshot,
            'selected_sequence':result['selected_sequence'],'candidate_distance':result['candidate_distance']}
        self.output_details=details;return details
    def validate_result(self,result):
        if type(result) is not dict or result.get('server_x4_motion_applied') is not True or result.get('server_apply_receipt') is not True:
            raise ValueError('server readback receipt missing')
        expected={'event':'result','ok':True,'tcp_admitted':True,'synthetic_server_checkpoint_and_admission':True,
            'client_authority_registered':True,'index':base.INDEX,'sector_macro':base.SECTOR,
            'server_x4_motion_applied':True,'server_apply_receipt':True,'frame_identity_proven':False}
        if set(result)!=set(expected)|{'samples','server_snapshot','candidate_distance','selected_sequence'} or any(
            type(result[k]) is not type(v) or result[k]!=v for k,v in expected.items()):raise ValueError('invalid worker result')
        snapshot=worker.snapshot_value(result['server_snapshot'],archive.REGISTRY_EPOCH)
        if snapshot!=self.server_snapshot:raise ValueError('server snapshot changed')
        samples=worker.sample_series(result['samples'],archive.REGISTRY_EPOCH,self.generation)
        if type(result['selected_sequence']) is not int or result['selected_sequence']!=len(samples):raise ValueError('candidate sequence differs')
        distances=[math.dist(snapshot['position'],[s[k] for k in ('x','y','z')]) for s in samples]
        if (any(5<=x<=50 for x in distances[:-1]) or not 5<=distances[-1]<=50 or
            type(result['candidate_distance']) not in (int,float) or result['candidate_distance']!=distances[-1]):
            raise ValueError('candidate selection differs')
        return samples
    def verify_final(self,logs):
        super().verify_final(logs)
        rows={role:frame.parse(logs[role],self.frame_nonces[role]) for role in ('server','client')}
        if frame.compare(rows['server'],rows['client'])!=self.frame_records:raise ValueError('frame observation changed')
        ship=rows['server']['ship']
        actual={'role':'server','nonce':self.frame_nonces['server'],'epoch':archive.REGISTRY_EPOCH,'index':base.INDEX,
            'code':ship['code'],'macro':ship['macro'],'faction':ship['faction'],'sector_macro':ship['sector'],
            'game_time':ship['game'],'position':list(ship['position'])}
        if actual!=self.server_snapshot:raise ValueError('server snapshot differs from final X4 log')
        sample=self.result['samples'][-1]
        # The immediate diagnostic is separately validated below; the existing
        # verifier still requires the later guarded MD/FFI readback.
        lines=logs['server'].splitlines(keepends=True)
        tag=b'[X4LAN] AUTH_MOTION_APPLY IMMEDIATE '
        immediate=[line for line in lines if tag in line]
        if len(immediate)!=1:raise ValueError('immediate readback missing')
        post_tag=b'[X4LAN] AUTH_MOTION_APPLY POST_OBSERVED '
        post=[line for line in lines if post_tag in line]
        if len(post)!=1:raise ValueError('later observation missing')
        filtered=b''.join(line for line in lines if tag not in line and post_tag not in line)
        report=setter.verify_apply(filtered,sample,[sample],['ready'])
        # Existing verifier names these for its original client-side caller;
        # both values here came from the server's local X4 game clock.
        report['server_game_before']=report.pop('client_game_before')
        report['server_game_after']=report.pop('client_game_after')
        report['readback_coordinate_process']='server'
        from authority.experimental_tcp_motion import motion_digest
        import math,re
        p=immediate[0].split(tag,1)[1].decode('ascii').strip().split()
        if (len(p)!=8 or not re.fullmatch('[0-9a-f]{32}',p[0]) or p[1:4]!=[str(sample['index']),str(sample['sequence']),motion_digest(sample)]):
            raise ValueError('immediate readback identity differs')
        xyz=[float(v) for v in p[4:7]];game=float(p[7])
        if not all(math.isfinite(x) for x in xyz+[game]):raise ValueError('invalid immediate readback')
        entered=b'[X4LAN] AUTH_MOTION_APPLY WRITE_ENTERED '+p[0].encode()
        later=b'[X4LAN] AUTH_MOTION_APPLY READBACK '+p[0].encode()
        if logs['server'].find(entered)<0 or not logs['server'].find(entered)<logs['server'].find(immediate[0])<logs['server'].find(later):
            raise ValueError('immediate readback ordering differs')
        report['immediate_readback']=xyz;report['immediate_server_game_time']=game
        q=post[0].split(post_tag,1)[1].decode('ascii').strip().split()
        if len(q)!=11 or q[:4]!=p[:4]:raise ValueError('later observation identity differs')
        values=[float(v) for v in q[4:]]
        if not all(math.isfinite(v) for v in values):raise ValueError('invalid later observation')
        observed=values[:3];post_game,write_game,elapsed,distance=values[3:]
        if (observed!=report['readback'] or post_game!=report['server_game_after'] or write_game!=report['server_game_before'] or
            elapsed<1 or elapsed>report['readback_elapsed'] or
            not math.isclose(distance,math.dist(observed,report['target']),rel_tol=1e-9,abs_tol=1e-6) or
            not logs['server'].find(immediate[0])<logs['server'].find(post[0])<logs['server'].find(later)):
            raise ValueError('later observation differs from readback')
        report['post_observed_elapsed']=elapsed;report['post_observed_distance']=distance
        self.output_details['setter_readback']=report
        return True
    def cleanup_after_owned_processes(self):
        try:return super().cleanup_after_owned_processes()
        finally:
            for r in self.roles.values():
                if 'motion' in r:r['motion'].close()

def run(args):
    args.defer_source_ack=True;args.two_clients=False;args.client_authority_index=base.INDEX;args.client_to_server_apply=True;active=[None]
    original=(lifecycle.coordinator.CensusCoordinator,lifecycle.installer.install,lifecycle.owned.spawn_owned_gated,lifecycle.load_observation)
    def make(candidates,*,defer_source_ack=False):
        active[0]=Coordinator(candidates,defer_source_ack=defer_source_ack);return active[0]
    def install_case(case,profile,ticket,config,nonce,timeout,window):return active[0].install(case,profile,ticket,config,nonce,timeout,window)
    def spawn(command,log,processes):
        result=original[2](command,log,processes);role=Path(log).parent.name
        if role not in ('server','client') or role in active[0].launches:raise ValueError('unexpected owned role')
        active[0].launches[role]=(result[0],result[1],args.game.resolve(strict=True));return result
    def load(raw,ticket,*,partial=False):
        if pair.private_fault(raw):raise ValueError('participant owner fault')
        return original[3](raw,ticket,partial=partial)
    try:
        lifecycle.coordinator.CensusCoordinator=make;lifecycle.installer.install=install_case
        lifecycle.owned.spawn_owned_gated=spawn;lifecycle.load_observation=load
        result=lifecycle.run(args)
        result.update(scope='disposable client-to-server one-shot local X4 readback',test_grant_synthetic=True,
            checkpoint_identity_proven=False,frame_identity_proven=False,clearance_proven=False,handover_proven=False,
            multiplayer_proven=False,setter_outcome_uncertain=not result['success'] and bool(active[0] and active[0].apply_possible))
        (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');return result
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
