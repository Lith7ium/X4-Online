#!/usr/bin/env python3
"""Opt-in two-X4 archived baseline readiness only; no network or Create."""
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
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.checkpoints import CheckpointStore, _read_regular
import authority_sector_read_live as base
import authority_sector_saved_fingerprint as saved
import authority_two_x4_live as owned
import authority_job_attach_live as readonly

TAG='[X4LAN] AUTH_SECTOR_PAIR '
MACRO=re.compile(r'[A-Za-z0-9_.-]{1,128}\Z',re.ASCII)
READY=re.compile(r'READY role=(server|client) nonce=([0-9a-f]{32}) game=('+base.NUMBER+r')\Z',re.ASCII)


def install(case,profile,ticket,role,nonce,macros,timeout):
    if (role not in ('server','client') or not re.fullmatch(r'[0-9a-f]{32}',nonce) or len(macros)!=2 or
        any(not isinstance(x,str) or not MACRO.fullmatch(x) or x in ('nil','null') for x in macros) or
        macros[0].casefold()==macros[1].casefold() or not math.isfinite(timeout) or timeout<60):
        raise ValueError('invalid private pair configuration')
    protected=base.install(case,profile,ticket,2)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    mdpath=md/'authority_sector_pair_ready.xml';uipath=ui/'authority_sector_pair_ready.lua'
    shutil.copyfile(ROOT/'tools/dev'/mdpath.name,mdpath);shutil.copyfile(ROOT/'tools/dev'/uipath.name,uipath)
    config=ui/'config.lua';text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected private configuration')
    config.write_text(text[:-2]+',authority_sector_pair_ready=true,authority_pair_role="'+role+'",authority_pair_nonce="'+nonce+
        '",authority_pair_deadline='+format(timeout,'.17g')+',authority_pair_macros={'+','.join('"'+x+'"' for x in macros)+'}}\n',encoding='ascii')
    config.chmod(0o600)
    read=ui/'authority_sector_read_probe.lua';text=read.read_text()
    text+='''\nfunction X4LAN_SECTOR_READ_EXPORT()
 if state~='done' or failed then error('read not complete') end
 guard()
 return first[4],first[5],first[2],sample.game
end
'''
    read.write_text(text)
    manifest=lab/'ui.xml';text=manifest.read_text();hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    if text.count(hook)!=1: raise ValueError('unexpected manifest')
    manifest.write_text(text.replace(hook,'    <file name="ui/authority_sector_pair_ready.lua" />\n'+hook))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text();hook=" if state=='done' then return end\n"
    if text.count(hook)!=1: raise ValueError('unexpected update owner')
    owner.write_text(text.replace(hook," if state=='done' then X4LAN_SECTOR_PAIR_TICK();return end\n"))
    if {p.name for p in md.iterdir()}!=set((*base.MD,'authority_sector_read_guard.xml',mdpath.name)):
        raise ValueError('unexpected private MD scripts')
    return protected+[mdpath,uipath]


def fault(raw):
    lower=raw.lower()
    return (base.fault_log(raw) or (TAG+'ERROR ').lower().encode() in lower or
            b'could not find suitable data type for conversion!' in lower or b'invalid data types for arithmetic operation!' in lower)


def validate(raw,ticket,role,nonce,*,partial=False):
    if fault(raw): raise ValueError('pair readiness probe fault')
    observation=base.check_log_bytes(raw,ticket,2,partial=partial)
    if observation is None:return None
    lines=raw.decode('utf-8').splitlines()
    ptag=base.load.TAG.decode()+'pause_observed|'
    pauses=[i for i,line in enumerate(lines) if ptag in line]
    rows=[(i,line.split(TAG,1)[1].strip()) for i,line in enumerate(lines) if TAG in line]
    if len(rows)>1 or rows and (len(pauses)!=1 or rows[0][0]<=pauses[0]): raise ValueError('reordered or duplicate pair readiness')
    if not rows:
        if partial:return None
        raise ValueError('missing pair readiness')
    m=READY.fullmatch(rows[0][1])
    if (not m or m[1]!=role or m[2]!=nonce or not math.isfinite(float(m[3])) or
        float(m[3])!=observation['reported_game_time']):raise ValueError('invalid readiness receipt')
    observation.update(role=role,baseline_registry_count=2,fixture_slots=2,local_ffi_checked=True,
        exact_loaded_file_proven=False,continuous_pause_proven=False,client_identity_proven=False)
    return observation


def file_identity(path):
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode): raise ValueError('staged save is not regular')
    return st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns


def run(args, participant=None):
    if sys.platform!='linux' or os.geteuid()==0: raise ValueError('unprivileged Linux required')
    out=base.snapshot.output_path(args.out);store=base.base.local_directory(args.store);src=store.parent
    if out.resolve().is_relative_to(src) or src.is_relative_to(out.resolve()):raise ValueError('output and source must be separate')
    if store!=base.archive.DEFAULT_STORE.resolve(strict=True):raise ValueError('only recorded archive supported')
    if not math.isfinite(args.timeout) or args.timeout<60 or not 0<=args.seed<=0xffffffff:raise ValueError('invalid timeout or seed')
    game=args.game.resolve(strict=True)
    if base.live.sha(game/'X4')!=base.live.EXE_SHA or not (game/'extensions').is_dir() or not shutil.which('bwrap'):
        raise ValueError('pinned X4 or bubblewrap unavailable')
    if base.live.x4_executables():raise ValueError('another X4 process is running')
    if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?',args.display):raise ValueError('local X11 display required')
    auth=Path(os.environ.get('XAUTHORITY',''))
    if not auth.is_file() or not os.access(auth,os.R_OK):raise ValueError('readable XAUTHORITY required')
    auth=auth.resolve(strict=True);user=pwd.getpwuid(os.geteuid());home=Path(user.pw_dir)
    steam=base.live.steam_identity(home,user.pw_uid)
    before=base.archive._path_fingerprints(store);origin=base.archive.verify(store)
    checkpoint=CheckpointStore(store).latest_confirmed();evidence=saved.verify(checkpoint,base.archive.REGISTRY_EPOCH)
    if base.archive._path_fingerprints(store)!=before:raise ValueError('archive changed during verification')
    slots=evidence['slots']
    if len(slots)!=2 or [r['index'] for r in slots]!=[1,2] or not evidence['sector_macros_unique_in_saved_universe']:
        raise ValueError('invalid saved fixture evidence')
    macros=[r['sector_macro'] for r in slots]
    out.mkdir(mode=0o700,parents=True,exist_ok=False)
    result={'success':False,'scope':'two isolated Linux X4 processes; archived baseline readiness only',
            'experiment_network_requested':False,'create_requested':False,'checkpoint_requested':False,
            'exact_loaded_file_proven':False,'continuous_pause_proven':False,'multiplayer_proven':False}
    if participant is not None:
        result.update(scope='two isolated Linux X4 processes; experimental participant',
                      experiment_network_requested=True,create_requested=True)
    roles={};processes=[];handlers={};lock_fd=lock_stat=None;cancellation=[None]
    def remember(number,frame):cancellation[0]=cancellation[0] or number
    def check_cancel():
        if cancellation[0] is not None:raise InterruptedError('signal '+str(cancellation[0]))
    try:
        for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):handlers[number]=signal.signal(number,remember)
        for role in ('server','client'):
            check_cancel()
            roleout=out/role;roleout.mkdir(mode=0o700)
            case,profile,binds,lock=base.snapshot.prepare_case(roleout,game,home)
            base.check_origin_scripts(store,profile)
            cp,target=base.base.stage_checkpoint(CheckpointStore(store),base.archive.CHECKPOINT_ID,profile)
            if (cp.sha256,cp.size)!=(origin['sha256'],origin['size']):raise ValueError('staged save differs from source')
            ticket=dict(world_epoch=secrets.token_hex(16),connection_handle=1,baseline_id=1,load_generation=1,
                checkpoint_id=cp.checkpoint_id,sha256=cp.sha256,attempt_id=secrets.token_hex(16),slot='save_009')
            nonce=secrets.token_hex(16);protected=install(case,profile,ticket,role,nonce,macros,args.timeout)
            if participant is not None:
                extra=participant.install(case,profile,ticket,role,nonce,macros,args.timeout)
                if type(extra) is not list:raise ValueError('invalid participant protected files')
                protected+=extra
                check_cancel()
            fingerprints={p:base.stable_read(p,1<<20,collect=False)[:2] for p in protected}
            target_digest=base.stable_read(target,origin['size'],collect=False)[:2]
            if target_digest[1]!=origin['sha256']:raise ValueError('staged save digest mismatch')
            base.check_origin_scripts(store,profile)
            for name in base.MD:
                if _read_regular(case/'extensions/x4_lan_lab/md'/name,1<<20)!=_read_regular(store.parent/'server/case/extensions/x4_lan_lab/md'/name,1<<20):
                    raise ValueError('private saved-state script differs from archive')
            command=readonly.readonly_save_command(case,game,binds,lock,args.display,auth,user.pw_name,args.seed,target)
            pos=command.index('--die-with-parent')
            for path in fingerprints:command[pos:pos]=['--ro-bind',str(path),str(path)];pos+=3
            roles[role]={'out':roleout,'case':case,'profile':profile,'ticket':ticket,'nonce':nonce,
                'protected':fingerprints,'target':target,'target_digest':target_digest,'target_id':file_identity(target),
                'command':command,'proc':None,'started':None,'identity':None,'log_snapshot':None,'observation':None}
        if base.archive._path_fingerprints(store)!=before:raise ValueError('archive changed while staging')
        check_cancel();lock_fd,lock_stat=base.live.create_lock_target(base.snapshot.LOCK_TARGET,user.pw_uid,user.pw_gid)
        check_cancel()
        if base.live.x4_executables() or base.live.steam_identity(home,user.pw_uid)!=steam:raise RuntimeError('process or Steam identity changed')
        deadline=time.monotonic()+args.timeout
        for role in ('server','client'):
            check_cancel();entry=roles[role]
            entry['proc'],entry['started']=owned.spawn_owned_gated(entry['command'],entry['out']/'process.log',processes)
            check_cancel()
        while True:
            check_cancel()
            if time.monotonic()>=deadline:raise TimeoutError('pair readiness deadline')
            if base.live.steam_identity(home,user.pw_uid)!=steam:raise RuntimeError('Steam identity changed')
            ready_round=set()
            for role,entry in roles.items():
                identity=base.load.game_identity(entry['proc'],entry['started'],game)
                if identity is not None:
                    if entry['identity'] is not None and entry['identity']!=identity:raise RuntimeError(role+' X4 changed')
                    entry['identity']=identity
                elif entry['identity'] is not None:raise RuntimeError(role+' X4 disappeared')
                if file_identity(entry['target'])!=entry['target_id']:raise ValueError(role+' staged save changed')
                if any(base.stable_read(p,1<<20,collect=False)[:2]!=v for p,v in entry['protected'].items()):
                    raise ValueError(role+' protected file changed')
                captured=base.read_live_log(entry['profile']/'engine-output.log',entry['log_snapshot'])
                if captured is None:continue
                raw,entry['log_snapshot']=captured
                if fault(raw):raise RuntimeError(role+' readiness fault')
                observation=validate(raw,entry['ticket'],role,entry['nonce'],partial=True)
                if observation is not None:
                    if entry['identity'] is None:raise RuntimeError(role+' receipt without owned X4')
                    entry['observation']=observation;ready_round.add(role)
            if ready_round=={'server','client'}:
                check_cancel()
                if time.monotonic()>=deadline or base.live.steam_identity(home,user.pw_uid)!=steam:raise RuntimeError('deadline or Steam identity changed')
                for role,e in roles.items():
                    if (base.load.game_identity(e['proc'],e['started'],game)!=e['identity'] or
                        base.stable_read(e['target'],origin['size'],collect=False)[:2]!=e['target_digest']):
                        raise RuntimeError(role+' context changed at readiness')
                check_cancel()
                if time.monotonic()>=deadline or base.live.steam_identity(home,user.pw_uid)!=steam:
                    raise RuntimeError('deadline or Steam identity changed after readiness')
                for role,e in roles.items():
                    if base.load.game_identity(e['proc'],e['started'],game)!=e['identity']:
                        raise RuntimeError(role+' X4 changed after readiness')
                def check_context():
                    check_cancel()
                    if time.monotonic()>=deadline or base.live.steam_identity(home,user.pw_uid)!=steam:
                        raise RuntimeError('deadline or Steam identity changed')
                    for current,e in roles.items():
                        if base.load.game_identity(e['proc'],e['started'],game)!=e['identity']:
                            raise RuntimeError(current+' X4 identity changed')
                        if file_identity(e['target'])!=e['target_id'] or any(
                            base.stable_read(p,1<<20,collect=False)[:2]!=v for p,v in e['protected'].items()):
                            raise ValueError(current+' protected input changed')
                        captured=base.read_live_log(e['profile']/'engine-output.log',e['log_snapshot'])
                        if captured is None:raise RuntimeError(current+' log observation unavailable')
                        raw,e['log_snapshot']=captured
                        if validate(raw,e['ticket'],current,e['nonce'],partial=True) is None:
                            raise RuntimeError(current+' readiness lost')
                        if participant.check_live_log(current,raw) is not True:
                            raise RuntimeError(current+' participant log fault')
                    check_cancel()
                    if time.monotonic()>=deadline:raise TimeoutError('pair deadline')
                    for current,e in roles.items():
                        if base.load.game_identity(e['proc'],e['started'],game)!=e['identity']:
                            raise RuntimeError(current+' X4 identity changed after context check')
                    check_cancel()
                    if time.monotonic()>=deadline:raise TimeoutError('pair deadline')
                    return True
                if participant is not None:
                    check_context()
                    details=participant.on_ready({'check':check_context,'deadline':deadline,'roles':roles,'macros':macros})
                    if type(details) is not dict:raise RuntimeError('participant completion unconfirmed')
                    check_context()
                    result['participant']=details
                result.update(success=True,profiles={r:e['observation'] for r,e in roles.items()});break
            time.sleep(.2)
    except BaseException as error:
        result.update(success=False,error=str(error) or type(error).__name__)
    finally:
        errors=[];remaining=[];stop_confirmed=True;remaining_known=True
        for number in handlers:
            try:signal.signal(number,signal.SIG_IGN)
            except BaseException as error:errors.append('cannot fence signals: '+type(error).__name__);stop_confirmed=False
        if cancellation[0] is not None:result.update(success=False,error='signal '+str(cancellation[0]))
        helper_confirmed=stop_confirmed if participant is not None else True
        if participant is not None:
            try:
                if participant.cleanup_before_owned_processes() is not True:raise RuntimeError('participant cleanup unconfirmed')
            except BaseException as error:
                helper_confirmed=False;stop_confirmed=False;errors.append('participant cleanup: '+type(error).__name__)
        for proc,started in (reversed(processes) if helper_confirmed else ()):
            try:
                if started is None:
                    if proc.poll() is None:proc.terminate();proc.wait(timeout=15)
                    errors.append('owned launcher identity unavailable')
                    remaining_known=False
                    if participant is not None:stop_confirmed=False
                else:
                    livepids=base.snapshot.stop_owned(proc,started)
                    if not isinstance(livepids,list) or any(type(x) is not int or x<=0 for x in livepids):raise RuntimeError('invalid cleanup result')
                    remaining.extend(livepids)
                    if livepids:stop_confirmed=False;errors.append('owned processes remain')
            except BaseException as error:stop_confirmed=False;remaining_known=False;errors.append('owned cleanup: '+type(error).__name__)
        result['owned_processes_remaining']=remaining if helper_confirmed and remaining_known else None
        result['owned_cleanup_confirmed']=stop_confirmed
        if errors:result.update(success=False,cleanup_errors=errors)
        if result['success']:
            try:
                final_logs={}
                for role,e in roles.items():
                    file_id,_,raw=base.stable_read(e['profile']/'engine-output.log',32<<20,collect=True)
                    base.log_continuity(file_id,raw,e['log_snapshot'])
                    validate(raw,e['ticket'],role,e['nonce'])
                    final_logs[role]=raw
                    if (base.stable_read(e['target'],origin['size'],collect=False)[:2]!=e['target_digest'] or
                        any(base.stable_read(p,1<<20,collect=False)[:2]!=v for p,v in e['protected'].items())):
                        raise ValueError(role+' final input changed')
                if base.archive._path_fingerprints(store)!=before:raise ValueError('source archive changed')
                if participant is not None and participant.verify_final(final_logs) is not True:
                    raise ValueError('participant final evidence unconfirmed')
            except BaseException as error:result.update(success=False,error='final evidence: '+(str(error) or type(error).__name__))
        if participant is not None:
            try:
                if participant.cleanup_after_owned_processes() is not True:raise RuntimeError('participant final cleanup unconfirmed')
            except BaseException as error:
                errors.append('participant final cleanup: '+type(error).__name__)
        if lock_stat is not None:
            if stop_confirmed:
                try:base.live.release_lock_target(base.snapshot.LOCK_TARGET,lock_fd,lock_stat)
                except BaseException as error:errors.append('lock cleanup: '+type(error).__name__)
            else:
                errors.append('lock retained: stop unconfirmed')
                try:os.close(lock_fd)
                except BaseException as error:errors.append('lock descriptor: '+type(error).__name__)
        try:
            if base.live.steam_identity(home,user.pw_uid)!=steam:errors.append('Steam identity changed')
        except BaseException as error:errors.append('Steam identity unavailable: '+type(error).__name__)
        if errors:result.update(success=False,cleanup_errors=errors)
        try:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        finally:
            for number,handler in handlers.items():
                try:signal.signal(number,handler)
                except BaseException:pass
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=base.archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--timeout',type=float,default=600);p.add_argument('--seed',type=int,default=276944566)
    try:result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error:p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__':sys.exit(main())
