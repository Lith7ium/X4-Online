#!/usr/bin/env python3
"""Isolated Linux download and load observation; no client admission or multiplayer.

A pre-existing verified checkpoint is republished by a synthetic server adapter,
then downloaded through SaveOffers into a fresh disposable X4 profile. The
session remains paused and no mark_loaded is called. It does not prove which
file X4 consumed, compatibility across machines, or an authentic server run.
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
import stat
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.checkpoints import CheckpointStore
from authority.save_transfer import SaveOffers, receive
from authority.world import WorldCoordinator
from lockstep.launcher import extension, joinfiles
import authority_load_live as base
import linux_gate_live as live
import linux_snapshot_capture as snapshot

FIELDS=('world_epoch','connection_handle','baseline_id','load_generation','checkpoint_id','sha256','attempt_id','slot')
TAG=b'[X4LAN] AUTH_DOWNLOAD_LOAD '

class ReceiptWatch(base.LoadWatch):
    def __init__(self,path,ticket):
        super().__init__(path)
        self.expected=[(event+'|'+ '|'.join(str(ticket[k]) for k in FIELDS)).encode('ascii')
                       for event in ('load_requested','pause_observed')]
    def poll(self):
        try: fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        except FileNotFoundError: return False
        try:
            st=os.fstat(fd); identity=(st.st_dev,st.st_ino)
            if not stat.S_ISREG(st.st_mode) or st.st_size<self.offset or st.st_size>self.MAX_LOG:
                raise ValueError('receipt log changed or exceeded limit')
            if self.identity is not None and self.identity!=identity: raise ValueError('receipt log replaced')
            self.identity=identity;os.lseek(fd,self.offset,os.SEEK_SET)
            for _ in range(4):
                chunk=os.read(fd,1<<20)
                if not chunk: break
                self.offset+=len(chunk);lines=(self.carry+chunk).split(b'\n');self.carry=lines.pop()
                if len(self.carry)>self.MAX_LINE: raise ValueError('receipt line too long')
                for line in lines:
                    if len(line)>self.MAX_LINE: raise ValueError('receipt line too long')
                    if TAG not in line: continue
                    row=line.split(TAG,1)[1].strip()
                    if self.stage>=2 or row!=self.expected[self.stage]:
                        raise ValueError('unexpected, duplicate, or mismatched receipt')
                    self.stage+=1
            return self.offset==os.fstat(fd).st_size and not self.carry
        finally: os.close(fd)


def install_probe(case,profile,ticket):
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui'
    if lab.is_symlink() or not lab.is_dir(): raise ValueError('private extension missing')
    (ui/'native_gate_snapshot.lua').unlink();(lab/'md/native_gate_battle.xml').unlink()
    for source,name in ((ROOT/'src/authority/lua/client_load_barrier.lua','client_load_barrier.lua'),
                        (ROOT/'src/authority/lua/x4_client_load_engine.lua','x4_client_load_engine.lua'),
                        (ROOT/'tools/dev/authority_download_load_probe.lua','authority_download_load_probe.lua')):
        shutil.copyfile(source,ui/name)
    files=[*extension.BASE_UI,'ui/client_load_barrier.lua','ui/x4_client_load_engine.lua','ui/authority_download_load_probe.lua']
    (lab/'ui.xml').write_text(extension.ui_xml(files),encoding='utf-8')
    config=ui/'config.lua';config.chmod(0o600)
    entries=','.join(k+'='+ (str(ticket[k]) if type(ticket[k]) is int else base.lua_literal(ticket[k])) for k in FIELDS)
    config.write_text('X4LAN_CONFIG = {enabled=false,test_profile="45841",authority_download_load=true,'
       'authority_load_save_path='+base.lua_literal(str(profile/'save'))+',authority_ticket={'+entries+'}}\n',encoding='ascii')
    return config


def stage_download(service,store,checkpoint,out,profile):
    """A real coordinator offer backed by a deliberately synthetic server."""
    class FakeServer:
        def pause(self): pass
        def save(self): return checkpoint.path
        def resume(self): raise RuntimeError('synthetic server cannot resume')
    offers=SaveOffers(service,store)
    world=WorldCoordinator(secrets.token_hex(16),FakeServer(),store,offers)
    handle=world.join('isolated-client')
    for expected in ('pause','save'):
        if world.session.pending is None or world.session.pending.operation!=expected: raise RuntimeError('unexpected coordinator state')
        world.step()
    offer=world.offer_load(handle)
    if offer.save.sha256!=checkpoint.sha256 or offer.save.size!=checkpoint.size:
        raise ValueError('republished checkpoint differs')
    ticket=dict(world_epoch=offer.world_epoch,connection_handle=offer.connection_handle,baseline_id=offer.baseline_id,
        load_generation=offer.load_generation,checkpoint_id=offer.save.checkpoint_id,sha256=offer.save.sha256,
        attempt_id=secrets.token_hex(16),slot='save_009')
    download=receive('127.0.0.1',service.port,service.token,1,offer.save,out/'download',retries=0,timeout=60)
    target=profile/'save'/snapshot.SLOT
    if any((profile/'save').iterdir()): raise ValueError('private save directory not empty')
    # Move within the private namespace and rehash the bytes offered to X4.
    download.rename(target);target.chmod(0o400)
    if target.stat().st_size!=offer.save.size or live.sha(target)!=ticket['sha256']:
        raise ValueError('staged download hash mismatch')
    return world,ticket,target


def game_identity(proc,started,game):
    if proc.poll() is not None or live.start_ticks(proc.pid)!=started: raise RuntimeError('owned launcher changed')
    identities=[]
    for pid in snapshot.owned_group_members(proc.pid,started):
        try:
            if os.path.samefile(f'/proc/{pid}/exe',game/'X4'): identities.append((pid,live.start_ticks(pid)))
        except (OSError,ValueError): continue
    if len(identities)>1: raise RuntimeError('multiple X4 processes in owned group')
    return identities[0] if identities else None


def run(args):
    if sys.platform!='linux' or os.geteuid()==0: raise ValueError('unprivileged Linux user required')
    out=snapshot.output_path(args.out);store_dir=base.local_directory(args.store);source_store=CheckpointStore(store_dir)
    checkpoint=source_store.latest()
    if checkpoint.checkpoint_id!=args.checkpoint_id: raise ValueError('requested checkpoint is not CURRENT')
    game=args.game.resolve(strict=True)
    if live.sha(game/'X4')!=live.EXE_SHA or not (game/'extensions').is_dir() or not shutil.which('bwrap'):
        raise ValueError('pinned X4 or bubblewrap unavailable')
    if live.x4_executables(): raise ValueError('another X4 process is running')
    if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?',args.display): raise ValueError('local X11 display required')
    auth=Path(os.environ.get('XAUTHORITY',''))
    if not auth.is_file() or not os.access(auth,os.R_OK): raise ValueError('readable XAUTHORITY required')
    auth=auth.resolve(strict=True)
    if not math.isfinite(args.timeout) or args.timeout<=0 or not 0<=args.seed<=0xffffffff: raise ValueError('invalid timeout or seed')
    user=pwd.getpwuid(os.geteuid());home=Path(user.pw_dir);steam=live.steam_identity(home,user.pw_uid)
    out.mkdir(mode=0o700,parents=True,exist_ok=False)
    result={'success':False,'scope':'one isolated Linux X4 client; localhost transfer; synthetic server; no admission'}
    proc=started=lock_fd=lock_stat=service=None;handlers={}
    try:
        case,profile,binds,lock=snapshot.prepare_case(out,game,home)
        saved_time=base.verify_origin(store_dir,checkpoint,profile)
        (out/'checkpoints').mkdir(mode=0o700);new_store=CheckpointStore(out/'checkpoints')
        token=secrets.token_hex(16);service=joinfiles.FileService(token,slots=(1,)).start()
        world,ticket,target=stage_download(service,new_store,checkpoint,out,profile)
        config=install_probe(case,profile,ticket)
        protected=[config,case/'extensions/x4_lan_lab/ui.xml',profile/'content.xml',profile/'config.xml']
        protected += [case/'extensions/x4_lan_lab/ui'/name for name in
                      ('client_load_barrier.lua','x4_client_load_engine.lua','authority_download_load_probe.lua')]
        expected={path:live.sha(path) for path in protected}
        lock_fd,lock_stat=live.create_lock_target(snapshot.LOCK_TARGET,user.pw_uid,user.pw_gid)
        for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP): handlers[number]=signal.signal(number,snapshot.cancel_capture)
        command=base.readonly_save_command(case,game,binds,lock,args.display,auth,user.pw_name,args.seed,target)
        pos=command.index('--die-with-parent')
        for path in protected:
            command[pos:pos]=['--ro-bind',str(path),str(path)];pos+=3
        with (out/'process.log').open('wb') as log:
            proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            started=live.start_ticks(proc.pid);deadline=time.monotonic()+args.timeout
            watch=ReceiptWatch(profile/'engine-output.log',ticket);seen_game=None
            while True:
                if time.monotonic()>=deadline: raise TimeoutError('client load observation timed out')
                identity=game_identity(proc,started,game)
                if identity is not None:
                    if seen_game is not None and identity!=seen_game: raise RuntimeError('X4 process changed')
                    seen_game=identity
                elif seen_game is not None: raise RuntimeError('X4 process disappeared')
                if any(live.sha(path)!=digest for path,digest in expected.items()):
                    raise ValueError('protected configuration changed')
                if live.steam_identity(home,user.pw_uid)!=steam: raise RuntimeError('Steam identity changed')
                caught_up=watch.poll()
                if watch.stage and seen_game is None: raise RuntimeError('receipt without owned X4 process')
                if caught_up and watch.stage==2:
                    if world.session.state!='paused' or world.session.ready_players: raise RuntimeError('unexpected admission')
                    result.update(success=True,transfer_verified=True,load_requested=True,pause_observed=True,
                        staged_save_read_only=True,configuration_read_only=True,saved_game_time=str(saved_time),
                        exact_loaded_file_proven=False,admitted=False)
                    break
                time.sleep(.1)
    except (Exception,KeyboardInterrupt) as error: result['error']=str(error)
    finally:
        if service is not None: service.close()
        if proc is not None and started is None and proc.poll() is None:
            try: proc.terminate();proc.wait(timeout=15)
            except (OSError,subprocess.TimeoutExpired): result.update(success=False,cleanup_error='launcher cleanup failed')
        if started is not None:
            try:
                remaining=snapshot.stop_owned(proc,started);result['owned_processes_remaining']=remaining
                if remaining: result.update(success=False,cleanup_error='owned processes remain')
            except (OSError,subprocess.TimeoutExpired): result.update(success=False,cleanup_error='process cleanup failed')
        if result['success']:
            try:
                while True:
                    old=watch.offset
                    if watch.poll(): break
                    if old==watch.offset: raise ValueError('incomplete receipt')
                if (watch.stage!=2 or live.sha(target)!=ticket['sha256'] or
                    any(live.sha(path)!=digest for path,digest in expected.items())):
                    raise ValueError('final receipt or configuration invalid')
            except (OSError,ValueError): result.update(success=False,error='final receipt or staged state invalid')
        if lock_stat is not None:
            try: live.release_lock_target(snapshot.LOCK_TARGET,lock_fd,lock_stat)
            except (OSError,RuntimeError): result.update(success=False,cleanup_error='lock cleanup failed')
        for number,handler in handlers.items(): signal.signal(number,handler)
        try:
            if live.steam_identity(home,user.pw_uid)!=steam: result.update(success=False,error='Steam identity changed')
        except (OSError,ValueError,RuntimeError): result.update(success=False,error='Steam identity unavailable')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--store',type=Path,required=True)
    p.add_argument('--checkpoint-id',required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--display',required=True);p.add_argument('--timeout',type=float,default=600)
    p.add_argument('--seed',type=int,default=276944566)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__': sys.exit(main())
