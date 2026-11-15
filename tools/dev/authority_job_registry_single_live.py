#!/usr/bin/env python3
"""One opt-in isolated X4 job-activation observation; never starts on import.

The only baseline is empty. Job activation is not proved birth, complete
coverage, delivery, client creation or multiplayer. Existing process namespace,
bridge and terminal lifecycle are reused; normal saves remain unmounted writable.
"""
import argparse
import json
import math
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_world_bridge_live as world_bridge
import authority_download_load_live as process_utils
import authority_job_registry_supervisor as supervisor
from authority.checkpoints import CheckpointStore
from authority.local_control_bridge import LocalControlBridge
from authority_control_cycle_evidence import read_cycle_evidence
import linux_gate_live as live
import linux_snapshot_capture as snapshot

_HEX=re.compile(r'[0-9a-f]{32}\Z')
_CLASS={'previously_observed','previously_unobserved_existing_index','new_registry_entry'}
_DONE={'inconclusive_no_events','local_activations_observed'}


def install(case,profile,*,bridge_port,bridge_lease,epoch,job_port,job_lease,window,request_timeout,capacity):
    if (not _HEX.fullmatch(bridge_lease) or not _HEX.fullmatch(epoch) or not _HEX.fullmatch(job_lease)
            or len({bridge_lease,epoch,job_lease})!=3 or not 1<=job_port<=65535
            or not math.isfinite(window) or not 1<=window<=180 or not math.isfinite(request_timeout)
            or not 0<request_timeout<=30 or type(capacity) is not int or not 1<=capacity<=1024):
        raise ValueError('invalid isolated job configuration')
    world_bridge.install_probe(case,bridge_port,bridge_lease,epoch)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    for filename in ('authority_ship_registry.xml','authority_job_ship_events.xml'):
        shutil.copyfile(ROOT/'tools/dev'/filename,md/filename)
    for filename in ('authority_job_registry_host.lua','authority_job_registry_probe.lua','authority_job_registry_single_probe.lua'):
        shutil.copyfile(ROOT/'tools/dev'/filename,ui/filename)
    cfg=ui/'config.lua';text=cfg.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected private configuration')
    suffix=(f', authority_job_single=true, authority_job_port={job_port}, authority_job_lease="{job_lease}",'
            f' authority_job_epoch="{epoch}", authority_job_save_path={json.dumps(str(profile/"save"))},'
            f' authority_job_window={window:.17g}, authority_job_timeout={request_timeout:.17g}, authority_job_capacity={capacity}')
    cfg.write_text(text[:-2]+suffix+'}\n',encoding='ascii');cfg.chmod(0o600)
    manifest=lab/'ui.xml';text=manifest.read_text(encoding='utf-8')
    hook='    <file name="ui/authority_world_bridge_probe.lua" />\n'
    if text.count(hook)!=1: raise ValueError('world bridge manifest hook missing')
    inserted=''.join(f'    <file name="ui/{name}" />\n' for name in (
        'authority_job_registry_probe.lua','authority_job_registry_host.lua','authority_job_registry_single_probe.lua'))
    manifest.write_text(text.replace(hook,inserted+hook),encoding='utf-8')
    bridge=ui/'authority_world_bridge_probe.lua';text=bridge.read_text(encoding='utf-8')
    hook=" local ok,reason=bridge:update();assert(ok,reason)\n"
    if text.count(hook)!=1: raise ValueError('bridge update hook missing')
    bridge.write_text(text.replace(hook,hook+' assert(X4LAN_JOB_REGISTRY_SINGLE_TICK)()\n'),encoding='utf-8')


class JobChannel:
    """Strictly ordered one-shot local channel; dropped receipts fail closed."""
    def __init__(self,sock,peer,lease,epoch,deadline,*,start_timeout=10):
        if (not isinstance(peer,tuple) or len(peer)!=2 or peer[0]!='127.0.0.1' or not _HEX.fullmatch(lease)
                or not _HEX.fullmatch(epoch) or not 0<start_timeout<=30): raise ValueError('invalid local channel')
        self.sock,self.peer,self.lease,self.epoch,self.deadline=sock,peer,lease,epoch,deadline
        self.start_timeout=start_timeout;self.started=False

    def _receive(self,timeout):
        if not math.isfinite(timeout) or timeout<=0: raise TimeoutError('job receipt deadline')
        end=min(self.deadline,time.monotonic()+timeout)
        while True:
            remaining=end-time.monotonic()
            if remaining<=0: raise TimeoutError('job receipt timed out')
            self.sock.settimeout(remaining)
            try: raw,peer=self.sock.recvfrom(769)
            except socket.timeout: raise TimeoutError('job receipt timed out') from None
            if peer!=self.peer: continue
            try: parts=raw.decode('ascii').split('|')
            except UnicodeError: raise ValueError('invalid job receipt encoding') from None
            if len(parts)<4 or parts[:3]!=['JOB',self.lease,self.epoch]: raise ValueError('invalid job receipt identity')
            if parts[3:] == ['HELLO']: continue
            if parts[3:] == ['FAULT']: raise RuntimeError('job host faulted')
            return parts[3:]

    def start(self):
        if self.started: raise RuntimeError('job start is one-shot')
        self.started=True
        self.sock.sendto(('JOBSTART|'+self.lease+'|'+self.epoch).encode('ascii'),self.peer)
        if self._receive(self.start_timeout)!=['STARTED']: raise ValueError('job start receipt invalid')

    def receive(self,timeout):
        if not self.started: raise RuntimeError('job channel not started')
        row=self._receive(timeout)
        if len(row)==4 and row[0]=='EVENT' and row[1].isdigit() and row[2].isdigit() and row[3] in _CLASS:
            return 'event',{'epoch':self.epoch,'sequence':int(row[1]),'index':int(row[2]),
                            'classification':row[3],'birth_confirmed':False,'delivery_confirmed':False}
        if len(row)==5 and row[0]=='DONE' and all(v.isdigit() for v in row[1:3]) and row[3]=='0' and row[4] in _DONE:
            return 'done',{'observed':int(row[1]),'acknowledged':int(row[2]),'baseline_count':int(row[3]),
                           'classification':row[4],'birth_confirmed':False,'delivery_confirmed':False,'coverage':'unknown'}
        raise ValueError('malformed or unexpected job receipt')


def run(args):
    if sys.platform!='linux' or os.geteuid()==0: raise ValueError('unprivileged Linux user required')
    out=snapshot.output_path(args.out);game=args.game.resolve(strict=True)
    if live.sha(game/'X4')!=live.EXE_SHA or not (game/'extensions').is_dir() or not shutil.which('bwrap'):
        raise ValueError('pinned game or bubblewrap unavailable')
    if live.x4_executables(): raise ValueError('another X4 process is running')
    if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?',args.display): raise ValueError('local X11 display required')
    auth=Path(os.environ.get('XAUTHORITY',''))
    if not auth.is_file() or not os.access(auth,os.R_OK): raise ValueError('readable XAUTHORITY required')
    auth=auth.resolve(strict=True)
    if (not math.isfinite(args.timeout) or args.timeout<=0 or not math.isfinite(args.window)
            or not 1<=args.window<=180 or not 0<=args.seed<=0xffffffff
            or args.timeout<args.window+50): raise ValueError('invalid timing or seed')
    user=pwd.getpwuid(os.geteuid());home=Path(user.pw_dir);steam=live.steam_identity(home,user.pw_uid)
    out.mkdir(mode=0o700,parents=True,exist_ok=False)
    result={'success':False,'lifecycle_success':False,'event_observed':False,'event_coverage_proven':False,
            'scope':'one isolated Linux X4; local job activations; no multiplayer',
            'empty_baseline':True,'universe_coverage_proven':False,'birth_confirmed':False,
            'delivery_confirmed':False,'checkpoint_requested':False}
    proc=started=lock_fd=lock_stat=None;handlers={};cleaned=False;case=None;installed=False
    bridge_sock=job_sock=None
    def cleanup():
        nonlocal cleaned
        if cleaned: return True
        if proc is None: cleaned=True;return True
        if started is None:
            if proc.poll() is None: proc.terminate();proc.wait(timeout=15)
            # No recorded process identity means group cleanup cannot be proved.
            return False
        remaining=snapshot.stop_owned(proc,started)
        if remaining: return False
        cleaned=True;return True
    try:
        bridge_sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        job_sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        bridge_sock.bind(('127.0.0.1',0));job_sock.bind(('127.0.0.1',0))
        bridge_sock.settimeout(.25);job_sock.settimeout(.25)
        lease,epoch,job_lease=secrets.token_hex(16),secrets.token_hex(16),secrets.token_hex(16)
        case,profile,binds,lock=snapshot.prepare_case(out,game,home)
        if any((profile/'save').iterdir()): raise RuntimeError('private save directory not empty')
        install(case,profile,bridge_port=bridge_sock.getsockname()[1],bridge_lease=lease,epoch=epoch,
                job_port=job_sock.getsockname()[1],job_lease=job_lease,window=args.window,request_timeout=5,capacity=128)
        installed=True
        (out/'checkpoints').mkdir(mode=0o700);store=CheckpointStore(out/'checkpoints')
        lock_fd,lock_stat=live.create_lock_target(snapshot.LOCK_TARGET,user.pw_uid,user.pw_gid)
        for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP): handlers[number]=signal.signal(number,snapshot.cancel_capture)
        with (out/'process.log').open('wb') as log:
            proc=subprocess.Popen(snapshot.command_for(case,game,binds,lock,args.display,auth,user.pw_name,args.seed),
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            started=live.start_ticks(proc.pid);deadline=time.monotonic()+args.timeout
            identity=None;bridge_peer=job_peer=None
            while bridge_peer is None or job_peer is None:
                if time.monotonic()>=deadline: raise TimeoutError('isolated probe handshake timed out')
                current=process_utils.game_identity(proc,started,game)
                if current is not None:
                    if identity is not None and identity!=current: raise RuntimeError('owned X4 changed')
                    identity=current
                elif identity is not None: raise RuntimeError('owned X4 disappeared')
                if live.steam_identity(home,user.pw_uid)!=steam: raise RuntimeError('Steam identity changed')
                for sock,kind,expected in ((bridge_sock,'bridge',f'HELLO|{lease}|{epoch}'),
                                           (job_sock,'job',f'JOB|{job_lease}|{epoch}|HELLO')):
                    try: data,peer=sock.recvfrom(769)
                    except socket.timeout: continue
                    if data==expected.encode('ascii') and peer[0]=='127.0.0.1':
                        if identity is None: raise RuntimeError('probe enrolled before owned X4')
                        if kind=='bridge':
                            if bridge_peer and bridge_peer!=peer: raise RuntimeError('bridge peer changed')
                            bridge_peer=peer
                        else:
                            if job_peer and job_peer!=peer: raise RuntimeError('job peer changed')
                            job_peer=peer
            bridge_timeout=min(10.,max(1.,args.timeout/20.))
            adapter=LocalControlBridge(enabled=True,sock=bridge_sock,peer=bridge_peer,lease=lease,world_epoch=epoch,
                profile=profile,store=store,verify_checkpoint=read_cycle_evidence,timeout=bridge_timeout)
            channel=JobChannel(job_sock,job_peer,job_lease,epoch,deadline)
            def check_owner():
                return process_utils.game_identity(proc,started,game)==identity and live.steam_identity(home,user.pw_uid)==steam
            remaining=deadline-time.monotonic()
            result['observation']=supervisor.supervise(bridge=adapter,channel=channel,check_owner=check_owner,
                cleanup=cleanup,epoch=epoch,timeout=remaining,bridge_timeout=bridge_timeout)
            # This path issues no checkpoint command; it does not prove that
            # no unrelated game mechanism wrote a private save file.
            result['observation'].pop('save_created',None)
            result['observation']['checkpoint_requested']=False
            result['success']=True
    except (Exception,KeyboardInterrupt) as error:
        result['error']=str(error)
    finally:
        try:
            if not cleanup(): result.update(success=False,cleanup_error='owned process cleanup unconfirmed')
        except (OSError,subprocess.TimeoutExpired,RuntimeError) as error:
            result.update(success=False,cleanup_error='owned process cleanup failed: '+str(error))
        if bridge_sock is not None: bridge_sock.close()
        if job_sock is not None: job_sock.close()
        if lock_stat is not None:
            try: live.release_lock_target(snapshot.LOCK_TARGET,lock_fd,lock_stat)
            except (OSError,RuntimeError): result.update(success=False,cleanup_error='lock cleanup failed')
        for number,handler in handlers.items(): signal.signal(number,handler)
        try:
            if live.steam_identity(home,user.pw_uid)!=steam: result.update(success=False,error='Steam identity changed')
        except (OSError,ValueError,RuntimeError): result.update(success=False,error='Steam identity unavailable')
        if case is not None:
            cfg=case/'extensions/x4_lan_lab/ui/config.lua'
            if cfg.is_file():
                try:
                    text=cfg.read_text(encoding='ascii')
                    counts=[]
                    for name in ('authority_control_lease','authority_job_lease'):
                        text,count=re.subn(name+r'="[0-9a-f]{32}"',name+'="redacted"',text)
                        counts.append(count)
                    cfg.write_text(text,encoding='ascii')
                    if any(count>1 or (installed and count!=1) for count in counts): raise ValueError('lease redaction failed')
                except (OSError,UnicodeError,ValueError): result.update(success=False,cleanup_error='lease cleanup failed')
        result['lifecycle_success']=result['success']
        result['event_observed']=bool(result['success'] and result['observation']['observed']>0)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--display',required=True);p.add_argument('--timeout',type=float,default=180)
    p.add_argument('--window',type=float,default=60);p.add_argument('--seed',type=int,default=276944566)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__': sys.exit(main())
