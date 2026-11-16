#!/usr/bin/env python3
"""Opt-in private Linux/Linux client→server NPC sample read; no launch on import.

The TCP world/admission and client test grant are synthetic. The server X4 is
not written, and this diagnostic does not implement HA ownership or handover.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import socket
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_source_tcp_pair_live as pair
import authority_source_motion_pair_live as motion_pair
import authority_census_replica_live as lifecycle
import authority_census_archive_provenance as archive
import authority_participant_job_install as participant_install
import authority_participant_client_authority_install as authority_install
import authority_sector_pair_transfer_live as transfer
from authority.experimental_tcp_motion import motion_value
from authority.experimental_motion_pair_evidence import validate_pair
from authority_helper_lifecycle import OwnedHelper
from authority_tcp_native_worker import parse_json

INDEX=1318
SECTOR='cluster_115_sector001_macro'
TAG='[X4LAN] AUTH_CLIENT_AUTHORITY SAMPLE '
ROW=re.compile(r'([1-9][0-9]*) ([1-9][0-9]*) ([A-Za-z0-9_]+) ([-+0-9.eE]+) ([-+0-9.eE]+) ([-+0-9.eE]+) ([-+0-9.eE]+)\Z',re.ASCII)

class ClientAuthorityCoordinator(pair.Coordinator):
    @staticmethod
    def _sources():
        paths=set(pair.Coordinator._sources())|{ROOT/'tools/dev'/name for name in (
            'authority_client_authority_pair_live.py','authority_client_authority_tcp_worker.py',
            'authority_client_authority_bind.py','authority_census_replica_live.py',
            'authority_participant_client_authority_install.py','authority_motion_ipc_supervisor.py',
            'authority_job_descriptor_probe.lua','authority_job_descriptor_probe.xml')}
        paths.update(ROOT/source for source,_ in authority_install.SCRIPTS)
        paths.update(ROOT/source for source,_,_ in participant_install.MODULES)
        paths.update(ROOT/'src/authority/lua'/name for name in ('client_load_barrier.lua','x4_client_load_engine.lua'))
        paths.update({ROOT/'tools/dev/authority_download_load_probe.lua',ROOT/'src/lockstep/base/ui/sha256.lua',
                      ROOT/'tools/dev/authority_multi_create_receiver.xml'})
        paths.update(archive.saved_state_script(name) for name in participant_install.BASE_MD)
        return tuple(sorted(paths))
    def __init__(self,candidates,*,defer_source_ack=False,sample_count=1):
        if type(sample_count) is not int or sample_count not in (1,2):raise ValueError('one or two samples required')
        matches=[sector for sector,values in candidates.items() if INDEX in values]
        if matches!=[SECTOR]:raise ValueError('pinned census index/sector identity differs')
        super().__init__(candidates,defer_source_ack=defer_source_ack)
        self.sample_count=sample_count;self.incarnation=self.fresh();self.grant_token=self.fresh()
    def add_role(self,role):
        result=super().add_role(role)
        if role=='client':
            try:
                sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
                r=self.roles[role];r.update(authority=sock,authority_lease=self.fresh(),authority_attempt=self.fresh(),
                    bootstrap_nonce=self.fresh(),sampler_nonce=self.fresh())
                while r['bootstrap_nonce'][:16]==r['sampler_nonce'][:16]:r['sampler_nonce']=self.fresh()
            except BaseException:
                if 'sock' in locals():sock.close()
                r=self.roles.pop(role);r['control'].close();r['job'].close();raise
        return result
    def install(self,case,profile,ticket,config,nonce,timeout,window):
        self.check_sources();role=config.get('role')
        if role not in self.roles or role in self.tickets or ticket['world_epoch']!=self.attempt:raise ValueError('private ticket differs')
        self.tickets[role]=dict(ticket);r=self.roles[role]
        settings={'participant_port':r['control'].getsockname()[1],'participant_lease':r['control_lease'],
            'job_port':r['job'].getsockname()[1],'lease':r['lease'],'attempt':r['attempt'],
            'epoch':archive.REGISTRY_EPOCH,'generation':self.generation,'nonce':r['nonce'],'seed':7183,'timeout':25}
        if role=='server':files=participant_install.install(case,profile,ticket,settings,self.witnesses)
        else:
            authority={'port':r['authority'].getsockname()[1],'lease':r['authority_lease'],'attempt':r['authority_attempt'],
             'bootstrap_nonce':r['bootstrap_nonce'],'sampler_nonce':r['sampler_nonce'],'token':self.grant_token,
             'incarnation':self.incarnation,'timeout':15,'interval':.1}
            files=authority_install.install(case,profile,ticket,settings,self.witnesses,authority)
            ui=Path(case)/'extensions/x4_lan_lab/ui';grant=ui/'client_authority_test_grant.lua'
            literal=participant_install.base.base.lua_literal
            # Static, explicit test assumption. The TCP worker independently
            # binds this grant to the actually admitted peer incarnation.
            grant.write_text('local e,g,t,n,w='+','.join(map(literal,(archive.REGISTRY_EPOCH,self.generation,self.grant_token,self.incarnation,self.attempt)))+'\n'+
              'function X4LAN_CLIENT_AUTHORITY_TEST_GRANT(a,b,i,x,y,z) return a==e and b==g and i==1318 and x==t and y==n and z==w end\n',encoding='ascii')
            grant.chmod(0o600);manifest=ui.parent/'ui.xml';hook='    <file name="ui/authority_download_load_probe.lua" />\n'
            manifest.write_text(transfer.once(manifest.read_text(),hook,'    <file name="ui/client_authority_test_grant.lua" />\n'+hook));files.append(grant)
        self.check_sources();return files
    def worker_config(self,r,server,client,deadline):
        return {'version':1,'epoch':self.attempt,'lease':r['lease'],'attempt':r['attempt'],'generation':self.generation,
         'participant_lease':r['control_lease'],'job_epoch':archive.REGISTRY_EPOCH,'client_process':client,'server_process':server,
         'deadline':deadline,'authority_lease':r['authority_lease'],'authority_attempt':r['authority_attempt'],
         'incarnation':self.incarnation,'grant_token':self.grant_token,'sample_count':self.sample_count}
    def run(self,context):
        if set(self.launches)!={'server','client'} or set(self.tickets)!={'server','client'}:raise RuntimeError('missing private pair')
        deadline=min(context['deadline']-5,time.monotonic()+110)
        if deadline-time.monotonic()<=40:raise TimeoutError('insufficient pair time')
        def guard():
            if context['check']() is not True or time.monotonic()>=deadline:raise RuntimeError('pair context changed')
            self.check_sources()
            if time.monotonic()>=deadline:raise TimeoutError('pair source check timed out')
            return True
        def identity(role):
            proc,started,game=self.launches[role];ident=lifecycle.base.load.game_identity(proc,started,game)
            if ident is None:raise RuntimeError('owned X4 unavailable')
            st=os.stat('/proc/'+str(ident[0])+'/exe')
            return {'pid':ident[0],'start_ticks':ident[1],'exe_dev':st.st_dev,'exe_ino':st.st_ino}
        guard();server=identity('server');client=identity('client');guard()
        if server['pid']==client['pid']:raise RuntimeError('X4 roles share PID')
        self.private,self.child=socket.socketpair();r=self.roles['client']
        sockets=(r['control'],r['job'],r['authority'],self.child);fds=tuple(s.fileno() for s in sockets)
        helper=OwnedHelper([sys.executable,str(ROOT/'tools/dev/authority_client_authority_tcp_worker.py'),*(str(fd) for fd in fds)],registry=self.helpers,pass_fds=fds)
        for sock in sockets:sock.close()
        cfg=self.worker_config(r,server,client,deadline)
        payload=json.dumps(cfg,separators=(',',':'),allow_nan=False).encode('ascii')+b'\n'
        if len(payload)>16384:raise ValueError('worker config too large')
        self.private.settimeout(min(2,deadline-time.monotonic()));self.private.sendall(payload);guard();helper.release();guard()
        reader=pair.ProgressFrames(self.private);result=parse_json(reader.read(deadline,guard));guard();self.validate_result(result)
        if helper.proc.wait(timeout=min(5,max(.01,deadline-time.monotonic())))!=0:raise RuntimeError('worker failed')
        motion_pair.finish_worker_output(self.private,reader,deadline,guard);guard();self.result=result
        return {'client_authority_registered':True,'client_authority_index':INDEX,'client_authority_sample_received':True,
         'server_x4_motion_applied':False,'checkpoint_identity_proven':False,'frame_identity_proven':False,
         'synthetic_tcp_checkpoint_and_admission':True,'samples':result['samples']}
    def validate_result(self,result):
        expected={'event':'result','ok':True,'tcp_admitted':True,'synthetic_server_checkpoint_and_admission':True,
         'client_authority_registered':True,'index':INDEX,'sector_macro':SECTOR,'server_x4_motion_applied':False,'frame_identity_proven':False}
        if type(result) is not dict or set(result)!=set(expected)|{'samples'} or any(type(result[k]) is not type(v) or result[k]!=v for k,v in expected.items()):
            raise ValueError('invalid client authority worker result')
        samples=result['samples']
        if type(samples) is not list or len(samples)!=self.sample_count:raise ValueError('client sample count differs')
        values=[motion_value(v) for v in samples]
        for n,v in enumerate(values,1):
            if v['epoch']!=archive.REGISTRY_EPOCH or v['generation']!=self.generation or v['index']!=INDEX or v['sequence']!=n or v['sector_macro']!=SECTOR:
                raise ValueError('client sample identity differs')
        if self.sample_count==1:
            if values[0]['velocity'] is not None:raise ValueError('first sample velocity must be unknown')
        else:validate_pair(values,epoch=archive.REGISTRY_EPOCH,generation=self.generation,index=INDEX,sector=SECTOR)
        return values
    def verify_final(self,logs):
        self.check_sources()
        if set(logs)!={'server','client'} or self.result is None:raise ValueError('missing final client authority evidence')
        for role in ('server','client'):
            if lifecycle.load_observation(logs[role],self.tickets[role]) is None:raise ValueError('load evidence missing')
        for raw in logs.values():
            if b'AUTH_PARTICIPANT_JOB LOCAL_APPLIED ' in raw:raise ValueError('unexpected job creation')
        running=False;running_time=None;rows=[]
        for line in logs['client'].decode('utf-8').splitlines():
            if '[X4LAN] AUTH_PARTICIPANT_JOB RUNNING ' in line:
                if running:raise ValueError('duplicate running marker')
                t=float(line.split('[X4LAN] AUTH_PARTICIPANT_JOB RUNNING ',1)[1])
                if not math.isfinite(t) or t<0:raise ValueError('invalid running marker')
                running=True;running_time=t
            if TAG in line:
                if not running:raise ValueError('sample before running marker')
                m=ROW.fullmatch(line.split(TAG,1)[1].strip())
                if not m:raise ValueError('invalid client sample marker')
                nums=tuple(map(float,m.groups()[3:]));
                if not all(math.isfinite(x) for x in nums) or nums[0]<=running_time:raise ValueError('sample did not advance client game time')
                rows.append((int(m[1]),int(m[2]),m[3],*nums))
        if not running:raise ValueError('client running marker missing')
        expected=[(v['index'],v['sequence'],v['sector_macro'],v['source_time'],v['x'],v['y'],v['z']) for v in self.result['samples']]
        if rows!=expected:raise ValueError('client marker/sample mismatch')
        if TAG.encode() in logs['server']:raise ValueError('unexpected server authority sample')
        return True
    def cleanup_after_owned_processes(self):
        try:return super().cleanup_after_owned_processes()
        finally:
            for r in self.roles.values():
                if 'authority' in r:r['authority'].close()


def run(args):
    args.defer_source_ack=True;args.two_clients=False;args.client_authority_index=INDEX;active=[None]
    original=(lifecycle.coordinator.CensusCoordinator,lifecycle.installer.install,lifecycle.owned.spawn_owned_gated,lifecycle.load_observation)
    def make(candidates,*,defer_source_ack=False):
        active[0]=ClientAuthorityCoordinator(candidates,defer_source_ack=defer_source_ack,sample_count=args.sample_count);return active[0]
    def install(case,profile,ticket,config,nonce,timeout,window):return active[0].install(case,profile,ticket,config,nonce,timeout,window)
    def spawn(command,log,processes):
        result=original[2](command,log,processes);role=Path(log).parent.name
        if role not in ('server','client') or role in active[0].launches:raise ValueError('unexpected owned role')
        active[0].launches[role]=(result[0],result[1],args.game.resolve(strict=True));return result
    def load(raw,ticket,*,partial=False):
        if pair.private_fault(raw):raise ValueError('participant owner fault')
        return original[3](raw,ticket,partial=partial)
    try:
        lifecycle.coordinator.CensusCoordinator=make;lifecycle.installer.install=install
        lifecycle.owned.spawn_owned_gated=spawn;lifecycle.load_observation=load
        result=lifecycle.run(args)
        result.update(scope='two isolated Linux X4; test-granted client NPC read to synthetic TCP server',
         test_grant_synthetic=True,checkpoint_identity_proven=False,frame_identity_proven=False,
         server_x4_motion_applied=False,handover_proven=False,multiplayer_proven=False)
        (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        return result
    finally:
        (lifecycle.coordinator.CensusCoordinator,lifecycle.installer.install,lifecycle.owned.spawn_owned_gated,lifecycle.load_observation)=original


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--timeout',type=float,default=300);p.add_argument('--window',type=float,default=60)
    p.add_argument('--seed',type=int,default=276944566);p.add_argument('--sample-count',type=int,choices=(1,2),default=1)
    try:r=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as e:p.exit(1,'REFUSED: '+str(e)+'\n')
    print(json.dumps(r,indent=2));return 0 if r['success'] else 1
if __name__=='__main__':sys.exit(main())
