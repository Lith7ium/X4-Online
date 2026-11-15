#!/usr/bin/env python3
"""One-shot MD warp of the first saved fixture in one isolated Linux X4 process.

Explicit diagnostic only. No normal profile is mounted writable. This experiment
may collide or crash, and does not attest atomicity or full-world synchronization.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'src'));sys.path.insert(0,str(REPO/'tools/dev'))
from lockstep.launcher import extension
import authority_load_live as load
import build_native_gate_overlay as builder
import linux_gate_live as live
import linux_snapshot_capture as snapshot


def stage_fixture(bundle, profile):
    bundle=load.local_directory(bundle)
    manifest=bundle/'manifest.json';source=bundle/'snapshot'/snapshot.SLOT
    if (manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size>4*1024*1024 or
        source.is_symlink() or not source.is_file()):
        raise ValueError('fixture bundle or snapshot unavailable')
    data=json.loads(manifest.read_text(encoding='utf-8'))
    digest=data.get('snapshot_sha256') if isinstance(data,dict) else None
    if (not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest) or
        not isinstance(data.get('files'),dict) or data['files'].get('snapshot/'+snapshot.SLOT)!=digest or
        live.sha(source)!=digest):
        raise ValueError('fixture snapshot does not match its bundle')
    save=profile/'save'
    if any(save.iterdir()): raise ValueError('new private save directory is not empty')
    target=save/snapshot.SLOT
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    fd=os.open(target,flags,0o600)
    try:
        with os.fdopen(fd,'wb') as dst,source.open('rb') as src:
            fd=-1;shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
    finally:
        if fd>=0:os.close(fd)
    if live.sha(target)!=digest or live.sha(source)!=digest:
        raise ValueError('fixture snapshot changed during staging')
    # Checks the actual serialized MD reference list and its twelve ship records;
    # without the native gate, no saved-ID-to-runtime mapping is attested.
    ids=builder.snapshot_fixture(target)
    if live.sha(target)!=digest: raise ValueError('fixture snapshot changed during validation')
    return target,digest,ids


def install_probe(case, profile):
    lab=case/'extensions/x4_lan_lab'
    if lab.is_symlink() or not lab.is_dir(): raise ValueError('private extension missing')
    ui=lab/'ui';md=lab/'md'
    if not (md/'native_gate_battle.xml').is_file(): raise ValueError('fixture MD missing')
    shutil.copyfile(REPO/'tools/dev/authority_fixture_warp_probe.lua',ui/'authority_fixture_warp_probe.lua')
    shutil.copyfile(REPO/'tools/dev/authority_fixture_warp.xml',md/'authority_fixture_warp.xml')
    (ui/'native_gate_snapshot.lua').unlink()
    (lab/'ui.xml').write_text(extension.ui_xml([*extension.BASE_UI,'ui/authority_fixture_warp_probe.lua']),encoding='utf-8')
    config=ui/'config.lua';config.chmod(0o600)
    config.write_text('X4LAN_CONFIG = {enabled=false, test_profile="45841", authority_fixture_warp=true, '
                      'authority_fixture_save_path='+load.lua_literal(str(profile/'save'))+'}\n',encoding='ascii')


class WarpWatch:
    TAG=b'[X4LAN] AUTH_WARP '
    NUMBER=rb'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'
    LABELS=(b'LOAD_ARMED',b'LOAD_REQUEST',b'LOADED',b'BEFORE',b'REQUEST',b'ACK',b'IMMEDIATE',b'LATE')
    MAX_LOG=256<<20;MAX_LINE=65536
    def __init__(self,path):
        self.path=path;self.offset=0;self.identity=None;self.carry=b'';self.stage=0;self.samples={}
    def poll(self):
        try:fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        except FileNotFoundError:return False
        try:
            info=os.fstat(fd);identity=(info.st_dev,info.st_ino)
            if (not stat.S_ISREG(info.st_mode) or info.st_size<self.offset or info.st_size>self.MAX_LOG or
                (self.identity is not None and self.identity!=identity)):
                raise ValueError('warp log changed or exceeded bounds')
            self.identity=identity;os.lseek(fd,self.offset,os.SEEK_SET)
            for _ in range(4):
                chunk=os.read(fd,1<<20)
                if not chunk:break
                self.offset+=len(chunk);lines=(self.carry+chunk).split(b'\n');self.carry=lines.pop()
                if len(self.carry)>self.MAX_LINE:raise ValueError('warp log line too long')
                for line in lines:
                    if len(line)>self.MAX_LINE:raise ValueError('warp log line too long')
                    if self.TAG not in line:continue
                    row=line.split(self.TAG,1)[1].strip()
                    if self.stage>=len(self.LABELS):raise ValueError('extra warp receipt')
                    name=self.LABELS[self.stage]
                    if name in (b'BEFORE',b'IMMEDIATE',b'LATE'):
                        pattern=name+rb' x=('+self.NUMBER+rb') y=('+self.NUMBER+rb') z=('+self.NUMBER+rb')'
                        if name==b'LATE':pattern+=rb' elapsed=('+self.NUMBER+rb')'
                        found=re.fullmatch(pattern,row)
                        if not found:raise ValueError('invalid or out-of-order warp measurement')
                        values=tuple(float(v) for v in found.groups())
                        if not all(math.isfinite(v) for v in values):raise ValueError('nonfinite warp measurement')
                        if name==b'LATE' and values[3]<1:raise ValueError('late readback too early')
                        self.samples[name.decode()]=values
                    elif row!=name:raise ValueError('invalid or out-of-order warp receipt')
                    self.stage+=1
            size=os.fstat(fd).st_size
            if size>self.MAX_LOG:raise ValueError('warp log exceeds bound')
            return self.offset==size and not self.carry
        finally:os.close(fd)


def check_measurements(watch):
    if watch.stage!=len(WarpWatch.LABELS):raise ValueError('incomplete warp receipts')
    before=watch.samples['BEFORE'];target=(before[0]+10,before[1],before[2])
    results={}
    for label,error_limit in (('IMMEDIATE',1.0),('LATE',3.0)):
        p=watch.samples[label]
        distance=math.dist(before[:3],p[:3]);error=math.dist(target,p[:3])
        if not math.isfinite(distance) or not math.isfinite(error) or not 5<=distance<=15 or error>error_limit:
            raise ValueError('warp displacement or target error outside bounds')
        results[label.lower()+'_displacement_m']=distance;results[label.lower()+'_target_error_m']=error
    results['late_delay_seconds']=watch.samples['LATE'][3]
    return results


def run(args):
    if sys.platform!='linux' or os.geteuid()==0:raise ValueError('run as unprivileged Linux Steam user')
    out=snapshot.output_path(args.out);bundle=load.local_directory(args.bundle)
    game=args.game.resolve(strict=True)
    if live.sha(game/'X4')!=live.EXE_SHA or not (game/'extensions').is_dir() or not shutil.which('bwrap'):
        raise ValueError('pinned game or bubblewrap unavailable')
    if live.x4_executables():raise ValueError('another X4 process is running')
    if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?',args.display):raise ValueError('local X11 display required')
    auth=Path(os.environ.get('XAUTHORITY',''))
    if not auth.is_file() or not os.access(auth,os.R_OK):raise ValueError('readable XAUTHORITY required')
    auth=auth.resolve(strict=True)
    if not math.isfinite(args.timeout) or args.timeout<=0 or not 0<=args.seed<=0xffffffff:
        raise ValueError('invalid timeout or seed')
    import pwd
    user=pwd.getpwuid(os.geteuid());home=Path(user.pw_dir);steam=live.steam_identity(home,user.pw_uid)
    out.mkdir(mode=0o700,parents=True,exist_ok=False);out.chmod(0o700)
    result={'success':False,'scope':'one disposable X4 instance, one MD fixture warp; no multiplayer',
            'collision_clearance_proven':False,'atomicity_proven':False,'runtime_saved_id_proven':False,
            'steam_before':steam}
    proc=started=lock_fd=lock_stat=None;handlers={}
    try:
        case,profile,binds,lock=snapshot.prepare_case(out,game,home)
        target,digest,ids=stage_fixture(bundle,profile)
        if len(ids)!=12:raise ValueError('snapshot fixture list incomplete')
        install_probe(case,profile)
        lock_fd,lock_stat=live.create_lock_target(snapshot.LOCK_TARGET,user.pw_uid,user.pw_gid)
        for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):handlers[number]=signal.signal(number,snapshot.cancel_capture)
        if live.sha(target)!=digest:raise ValueError('snapshot changed before launch')
        with (out/'process.log').open('wb') as log:
            command=load.readonly_save_command(case,game,binds,lock,args.display,auth,user.pw_name,args.seed,target)
            proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            started=live.start_ticks(proc.pid);deadline=time.monotonic()+args.timeout
            watch=WarpWatch(profile/'engine-output.log')
            while True:
                if time.monotonic()>=deadline:raise TimeoutError('fixture warp experiment timed out')
                if proc.poll() is not None:raise RuntimeError('owned X4 exited before warp completion')
                if live.steam_identity(home,user.pw_uid)!=steam:raise RuntimeError('Steam identity changed')
                caught_up=watch.poll()
                if caught_up and watch.stage==len(WarpWatch.LABELS):
                    measurements=check_measurements(watch)
                    if live.sha(target)!=digest:raise ValueError('snapshot changed during experiment')
                    result.update(success=True,snapshot_sha256=digest,saved_reference_list_validated=True,**measurements)
                    break
                time.sleep(.1)
    except (Exception,KeyboardInterrupt) as error:result['error']=str(error)
    finally:
        if proc is not None and started is None and proc.poll() is None:
            try:proc.terminate();proc.wait(timeout=15)
            except (OSError,subprocess.TimeoutExpired):result.update(success=False,cleanup_error='unidentified launcher cleanup failed')
        if started is not None:
            try:
                remaining=snapshot.stop_owned(proc,started);result['owned_processes_remaining']=remaining
                if remaining:result.update(success=False,cleanup_error='owned process group remains')
            except (OSError,subprocess.TimeoutExpired):result.update(success=False,cleanup_error='owned process cleanup failed')
        if result['success']:
            try:
                while True:
                    previous=watch.offset
                    if watch.poll():break
                    if watch.offset==previous:raise ValueError('incomplete final log line')
                check_measurements(watch)
            except (OSError,ValueError):result.update(success=False,error='final warp receipt invalid')
        if lock_stat is not None:
            try:live.release_lock_target(snapshot.LOCK_TARGET,lock_fd,lock_stat)
            except (OSError,RuntimeError):result.update(success=False,cleanup_error='lock cleanup failed')
        for number,handler in handlers.items():signal.signal(number,handler)
        try:result['steam_after']=live.steam_identity(home,user.pw_uid)
        except (OSError,ValueError,RuntimeError):result['steam_after']=None
        if result['steam_after']!=steam:result.update(success=False,error='Steam identity changed')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True);parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--display',required=True)
    parser.add_argument('--timeout',type=float,default=600);parser.add_argument('--seed',type=int,default=276944566)
    args=parser.parse_args(argv)
    try:result=run(args)
    except (OSError,ValueError,RuntimeError) as error:parser.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__':sys.exit(main())
