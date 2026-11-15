#!/usr/bin/env python3
"""Opt-in one-X4 ResolveV2 table diagnostic; import never starts X4."""
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
import linux_gate_live as live
import linux_snapshot_capture as snapshot
from authority.checkpoints import CheckpointStore
from authority.local_control_bridge import LocalControlBridge
from authority_control_cycle_evidence import read_cycle_evidence

HEX=re.compile(r'[0-9a-f]{32}\Z')


def install(case,profile,*,port,lease,epoch,id1,id2):
    if any(not HEX.fullmatch(x) for x in (lease,epoch,id1,id2)) or len({lease,epoch,id1,id2})!=4:
        raise ValueError('invalid isolated probe tokens')
    world_bridge.install_probe(case,port,lease,epoch)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui'
    for name in ('authority_ship_registry.xml','authority_registry_resolve_v2.xml'):
        shutil.copyfile(ROOT/'tools/dev'/name,lab/'md'/name)
    for source,target in ((ROOT/'src/authority/lua/x4_ship_engine.lua','x4_ship_engine.lua'),
                          (ROOT/'tools/dev/authority_registry_resolve_v2.lua','authority_registry_resolve_v2.lua'),
                          (ROOT/'tools/dev/authority_registry_resolve_v2_native.lua','authority_registry_resolve_v2_native.lua')):
        shutil.copyfile(source,ui/target)
    config=ui/'config.lua';text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected probe config')
    suffix=(f', authority_resolve_v2_native=true, authority_resolve_epoch="{epoch}",'
            f' authority_resolve_id1="{id1}", authority_resolve_id2="{id2}",'
            f' authority_resolve_save_path={json.dumps(str(profile/"save"))}')
    config.write_text(text[:-2]+suffix+'}\n',encoding='ascii');config.chmod(0o600)
    manifest=lab/'ui.xml';text=manifest.read_text(encoding='utf-8')
    hook='    <file name="ui/authority_world_bridge_probe.lua" />\n'
    if text.count(hook)!=1: raise ValueError('missing manifest hook')
    added=''.join(f'    <file name="ui/{name}" />\n' for name in ('x4_ship_engine.lua',
        'authority_registry_resolve_v2.lua','authority_registry_resolve_v2_native.lua'))
    manifest.write_text(text.replace(hook,added+hook),encoding='utf-8')
    bridge=ui/'authority_world_bridge_probe.lua';text=bridge.read_text(encoding='utf-8')
    hook=' if not started and now-loaded_at>=3 then\n'
    if text.count(hook)!=1: raise ValueError('missing bridge hook')
    text=text.replace(hook,' if not started and now-loaded_at>=3 and not X4LAN_RESOLVE_V2_NATIVE_READY() then return end\n'+hook)
    bridge.write_text(text,encoding='utf-8')


def check_log(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>32<<20: raise ValueError('invalid probe log')
    tag='[X4LAN] AUTH_RESOLVE_V2 '
    rows=[line.split(tag,1)[1].strip() for line in path.read_text(encoding='utf-8',errors='strict').splitlines() if tag in line]
    if any(row.startswith('ERROR ') for row in rows): raise ValueError('native probe fault')
    if (len(rows)!=5 or not rows[0].startswith('SHAPE stage=ok type=table ') or rows[1]!='ACTOR_MATCH'
            or not rows[2].startswith('SHAPE stage=unavailable type=table ')
            or rows[3:]!=['UNAVAILABLE','DONE']):
        raise ValueError('missing, duplicate or reordered native receipts')
    return {'actor_match_observed':True,'correlated_unavailable_observed':True,'shape_rows':[rows[0],rows[2]]}


def probe_fault(path):
    if not path.exists(): return False
    if path.is_symlink() or not path.is_file() or path.stat().st_size>32<<20: raise ValueError('invalid probe log')
    with path.open('rb') as stream:
        stream.seek(max(0,path.stat().st_size-(1<<16)))
        return b'[X4LAN] AUTH_RESOLVE_V2 ERROR ' in stream.read(1<<16)


def pause_timeout(remaining):
    if not math.isfinite(remaining) or remaining<2.:
        raise TimeoutError('insufficient pause deadline and cleanup reserve')
    return min(10.,remaining-1.)


def run(args):
    if sys.platform!='linux' or os.geteuid()==0: raise ValueError('unprivileged Linux user required')
    out=snapshot.output_path(args.out);game=args.game.resolve(strict=True)
    if live.sha(game/'X4')!=live.EXE_SHA or not (game/'extensions').is_dir() or not shutil.which('bwrap'):
        raise ValueError('pinned X4 or bubblewrap unavailable')
    if live.x4_executables(): raise ValueError('another X4 process is running')
    if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?',args.display): raise ValueError('local X11 display required')
    auth=Path(os.environ.get('XAUTHORITY',''))
    if not auth.is_file() or not os.access(auth,os.R_OK): raise ValueError('readable XAUTHORITY required')
    auth=auth.resolve(strict=True)
    if not math.isfinite(args.timeout) or args.timeout<30 or not 0<=args.seed<=0xffffffff: raise ValueError('invalid timeout or seed')
    user=pwd.getpwuid(os.geteuid());home=Path(user.pw_dir);steam=live.steam_identity(home,user.pw_uid)
    out.mkdir(mode=0o700,parents=True,exist_ok=False)
    result={'success':False,'scope':'one isolated Linux X4; local table diagnostic; no multiplayer',
            'checkpoint_requested':False,'runtime_binding_proven':False,'universe_coverage_proven':False}
    proc=started=lock_fd=lock_stat=sock=None;case=None;handlers={};installed=False
    try:
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));sock.settimeout(.25)
        lease,epoch,id1,id2=(secrets.token_hex(16) for _ in range(4))
        case,profile,binds,lock=snapshot.prepare_case(out,game,home)
        if any((profile/'save').iterdir()): raise RuntimeError('private save directory not empty')
        install(case,profile,port=sock.getsockname()[1],lease=lease,epoch=epoch,id1=id1,id2=id2);installed=True
        (out/'checkpoints').mkdir(mode=0o700);store=CheckpointStore(out/'checkpoints')
        lock_fd,lock_stat=live.create_lock_target(snapshot.LOCK_TARGET,user.pw_uid,user.pw_gid)
        for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP): handlers[number]=signal.signal(number,snapshot.cancel_capture)
        with (out/'process.log').open('wb') as log:
            proc=subprocess.Popen(snapshot.command_for(case,game,binds,lock,args.display,auth,user.pw_name,args.seed),
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            started=live.start_ticks(proc.pid);deadline=time.monotonic()+args.timeout
            peer=identity=None
            while peer is None:
                if time.monotonic()>=deadline: raise TimeoutError('ResolveV2/bridge handshake deadline')
                current=process_utils.game_identity(proc,started,game)
                if current is not None:
                    if identity is not None and identity!=current: raise RuntimeError('owned X4 changed')
                    identity=current
                elif identity is not None: raise RuntimeError('owned X4 disappeared')
                if live.steam_identity(home,user.pw_uid)!=steam: raise RuntimeError('Steam identity changed')
                if probe_fault(profile/'engine-output.log'): raise RuntimeError('native ResolveV2 probe failed; inspect private log')
                try: data,address=sock.recvfrom(769)
                except socket.timeout: continue
                if data==f'HELLO|{lease}|{epoch}'.encode() and address[0]=='127.0.0.1':
                    if identity is None: raise RuntimeError('handshake without owned X4')
                    peer=address
            left=deadline-time.monotonic()
            adapter=LocalControlBridge(enabled=True,sock=sock,peer=peer,lease=lease,world_epoch=epoch,
                profile=profile,store=store,verify_checkpoint=read_cycle_evidence,timeout=pause_timeout(left))
            if process_utils.game_identity(proc,started,game)!=identity or live.steam_identity(home,user.pw_uid)!=steam:
                raise RuntimeError('identity changed before pause')
            adapter.pause()
            if time.monotonic()>deadline or process_utils.game_identity(proc,started,game)!=identity or live.steam_identity(home,user.pw_uid)!=steam:
                raise RuntimeError('identity or deadline changed during pause')
            result.update(check_log(profile/'engine-output.log'));result['native_pause_confirmed']=True;result['success']=True
    except (Exception,KeyboardInterrupt) as error:
        result['error']=str(error)
    finally:
        if sock is not None: sock.close()
        if proc is not None:
            try:
                if started is None:
                    if proc.poll() is None: proc.terminate();proc.wait(timeout=15)
                    result.update(success=False,cleanup_error='owned process identity unavailable')
                else:
                    remaining=snapshot.stop_owned(proc,started)
                    if remaining: result.update(success=False,cleanup_error='owned processes remain')
                    else: result['owned_cleanup_confirmed']=True
            except (OSError,subprocess.TimeoutExpired): result.update(success=False,cleanup_error='owned cleanup failed')
        if result.get('success'):
            try: result.update(check_log(profile/'engine-output.log'))
            except (OSError,UnicodeError,ValueError) as error: result.update(success=False,error='final log invalid: '+str(error))
        if lock_stat is not None:
            try: live.release_lock_target(snapshot.LOCK_TARGET,lock_fd,lock_stat)
            except (OSError,RuntimeError): result.update(success=False,cleanup_error='lock cleanup failed')
        for number,handler in handlers.items(): signal.signal(number,handler)
        try:
            if live.steam_identity(home,user.pw_uid)!=steam: result.update(success=False,error='Steam identity changed')
        except (OSError,ValueError,RuntimeError): result.update(success=False,error='Steam identity unavailable')
        if case is not None:
            config=case/'extensions/x4_lan_lab/ui/config.lua'
            if config.is_file():
                try:
                    text=config.read_text(encoding='ascii')
                    redacted,count=re.subn(r'authority_control_lease="[0-9a-f]{32}"','authority_control_lease="redacted"',text)
                    if count>1 or (installed and count!=1): raise ValueError('invalid lease')
                    config.write_text(redacted,encoding='ascii')
                except (OSError,UnicodeError,ValueError): result.update(success=False,cleanup_error='lease cleanup failed')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
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
