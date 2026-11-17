#!/usr/bin/env python3
"""Opt-in two-X4 census descriptor/witness diagnostic; no game on import."""
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
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
from authority.checkpoints import _read_regular
import authority_census_archive_provenance as archive
import authority_census_runtime_read_live as census
import authority_census_pair_inputs as inputs
import authority_census_pair_install as installer
import authority_census_pair_coordinator as coordinator
import authority_job_attach_live as readonly
import authority_sector_read_live as base
import authority_sector_pair_live as pair
import authority_sector_pair_transfer_live as pair_transfer
import authority_two_x4_live as owned


def verify_saved_overlay(case, store):
    """Require each installed saved-state script to match the archive."""
    for name in installer._BASE_MD:
        installed = case/'extensions/x4_lan_lab/md'/name
        archived = store.parent/'server/case/extensions/x4_lan_lab/md'/name
        if _read_regular(installed, 1 << 20) != _read_regular(archived, 1 << 20):
            raise ValueError('saved-state overlay differs from archive')


def load_observation(raw,ticket,*,partial=False):
    lowered=raw.lower()
    if (base.fault_log(raw) or b'[x4lan] auth_census_job error fault' in lowered
        or b'could not find suitable data type for conversion!' in lowered
        or b'invalid data types for arithmetic operation!' in lowered):
        raise ValueError('load or census owner fault')
    if not raw.endswith(b'\n'):
        if partial:return None
        raise ValueError('incomplete engine log')
    tags=(base.load.TAG.decode(),'[X4LAN] AUTH_MARKER load ')
    rows=[]
    for line in raw.decode('utf-8').splitlines():
        for tag in tags:
            if tag in line:rows.append((tag,line.split(tag,1)[1].strip()))
    fields='|'.join(str(ticket[k]) for k in base.load.FIELDS)
    expected=[(tags[0],'load_requested|'+fields),(tags[1],'INSPECTED '+archive.MARKER),
              (tags[0],'pause_observed|'+fields)]
    if rows!=expected[:len(rows)] or len(rows)>len(expected):raise ValueError('invalid or reordered load receipts')
    if len(rows)<len(expected):
        if partial:return None
        raise ValueError('incomplete load receipts')
    return {'marker_checked':True,'initial_pause_checked':True,'baseline_expected':archive.COUNT,
            'exact_loaded_file_proven':False,'continuous_pause_proven':False}


def run(args):
    if sys.platform!='linux' or os.geteuid()==0:raise ValueError('unprivileged Linux required')
    out=base.snapshot.output_path(args.out);store=base.base.local_directory(args.store)
    census.ensure_separate(out,store)
    target_out=out.resolve();witness=inputs.WITNESS_PATH.resolve(strict=True)
    if target_out.is_relative_to(witness) or witness.is_relative_to(target_out):raise ValueError('output overlaps witness input')
    if not math.isfinite(args.window) or not 1<=args.window<=180 or not math.isfinite(args.timeout) or not args.window+90<=args.timeout<=600:
        raise ValueError('invalid diagnostic window or deadline')
    if type(args.seed) is not int or not 0<=args.seed<=0xffffffff:raise ValueError('invalid X4 seed')
    game=args.game.resolve(strict=True)
    if base.live.sha(game/'X4')!=base.live.EXE_SHA or not (game/'extensions').is_dir() or not shutil.which('bwrap'):
        raise ValueError('pinned X4 or bubblewrap unavailable')
    if base.live.x4_executables():raise ValueError('another X4 process is running')
    if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?',args.display):raise ValueError('local X11 display required')
    auth=Path(os.environ.get('XAUTHORITY',''))
    if not auth.is_file() or not os.access(auth,os.R_OK):raise ValueError('readable XAUTHORITY required')
    auth=auth.resolve(strict=True);user=pwd.getpwuid(os.geteuid());home=Path(user.pw_dir)
    steam=base.live.steam_identity(home,user.pw_uid)
    out.mkdir(mode=0o700,parents=True,exist_ok=False)
    result={'success':False,'scope':'two isolated Linux X4; census descriptor to local witness only',
            'checkpoint_requested':False,'ship_creation_requested':False,'multiplayer_proven':False,
            'continuous_pause_proven':False,'exact_loaded_file_proven':False,'runtime_frame_identity_proven':False}
    processes=[];roles={};handlers={};lock_fd=lock_stat=None;cancel=[None];coord=None;verified=None;compiler_error=None;no_event=False
    def remember(number,frame):cancel[0]=cancel[0] or number
    def check_cancel():
        if cancel[0] is not None:raise InterruptedError('signal '+str(cancel[0]))
    try:
        for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):handlers[number]=signal.signal(number,remember)
        check_cancel();verified=inputs.verify_once(store);check_cancel()
        result.update(source_checkpoint_id=archive.CHECKPOINT_ID,source_sha256=archive.SHA256,
                      registry_epoch=archive.REGISTRY_EPOCH,witness_artifact_sha256=verified.witness_sha256)
        coord=coordinator.CensusCoordinator(verified.witness_candidates)
        for role in ('server','client'):
            check_cancel();roleout=out/role;roleout.mkdir(mode=0o700)
            case,profile,binds,lock=base.snapshot.prepare_case(roleout,game,home)
            census.origin_scripts(store,profile)
            roles[role]={'out':roleout,'case':case,'profile':profile,'binds':binds,'lock':lock,
                         'proc':None,'started':None,'identity':None,'log_snapshot':None}
        staged=inputs.stage_pair(verified,{r:e['profile'] for r,e in roles.items()})
        for role,e in roles.items():
            check_cancel();target,fp,sha=staged[role]
            ticket={'world_epoch':coord.attempt,'connection_handle':1,'baseline_id':1,'load_generation':1,
                    'checkpoint_id':archive.CHECKPOINT_ID,'sha256':archive.SHA256,
                    'attempt_id':secrets.token_hex(16),'slot':'save_009'}
            config=coord.add_role(role);nonce=secrets.token_hex(16)
            try:protected=installer.install(e['case'],e['profile'],ticket,config,nonce,args.timeout,args.window)
            except pair_transfer.CompilerCleanupUnconfirmed as error:
                compiler_error=error;raise
            check_cancel()
            fingerprints={p:base.stable_read(p,1<<20,collect=False)[:2] for p in protected}
            census.origin_scripts(store,e['profile'])
            verify_saved_overlay(e['case'], store)
            command=readonly.readonly_save_command(e['case'],game,e['binds'],e['lock'],args.display,auth,user.pw_name,args.seed,target)
            pos=command.index('--die-with-parent')
            for path in fingerprints:command[pos:pos]=['--ro-bind',str(path),str(path)];pos+=3
            e.update(ticket=ticket,nonce=nonce,protected=fingerprints,target=target,target_digest=(fp,sha),
                     target_id=pair.file_identity(target),command=command)
        if archive.fingerprints(store)!=verified.archive_fingerprints:raise ValueError('archive changed while preparing')
        check_cancel();lock_fd,lock_stat=base.live.create_lock_target(base.snapshot.LOCK_TARGET,user.pw_uid,user.pw_gid)
        check_cancel()
        if base.live.x4_executables() or base.live.steam_identity(home,user.pw_uid)!=steam:raise RuntimeError('process or Steam identity changed')
        deadline=time.monotonic()+args.timeout
        def check_before_launch():
            check_cancel()
            if time.monotonic()>=deadline or base.live.steam_identity(home,user.pw_uid)!=steam:
                raise RuntimeError('deadline or Steam identity changed before launch')
            if archive.fingerprints(store)!=verified.archive_fingerprints:raise ValueError('archive changed before launch')
            for role,e in roles.items():
                if (pair.file_identity(e['target'])!=e['target_id'] or
                    base.stable_read(e['target'],archive.SIZE,collect=False)[:2]!=e['target_digest'] or
                    any(base.stable_read(p,1<<20,collect=False)[:2]!=v for p,v in e['protected'].items())):
                    raise ValueError(role+' staged input changed before launch')
            check_cancel()
            if time.monotonic()>=deadline or base.live.steam_identity(home,user.pw_uid)!=steam:
                raise RuntimeError('deadline or Steam identity changed after launch guard')
        for role,e in roles.items():
            check_before_launch()
            e['proc'],e['started']=owned.spawn_owned_gated(e['command'],e['out']/'process.log',processes);check_cancel()
        def inspect_context(*,require_load):
            check_cancel()
            if time.monotonic()>=deadline or base.live.steam_identity(home,user.pw_uid)!=steam:
                raise RuntimeError('deadline or Steam identity changed')
            if archive.fingerprints(store)!=verified.archive_fingerprints:raise ValueError('archive changed during run')
            ready=set()
            for role,e in roles.items():
                identity=base.load.game_identity(e['proc'],e['started'],game)
                if identity is not None:
                    if e['identity'] is not None and e['identity']!=identity:raise RuntimeError(role+' X4 changed')
                    e['identity']=identity
                elif e['identity'] is not None:raise RuntimeError(role+' X4 disappeared')
                if pair.file_identity(e['target'])!=e['target_id'] or any(
                    base.stable_read(p,1<<20,collect=False)[:2]!=v for p,v in e['protected'].items()):
                    raise ValueError(role+' protected input changed')
                captured=base.read_live_log(e['profile']/'engine-output.log',e['log_snapshot'])
                if captured is None:
                    if require_load:raise RuntimeError(role+' log observation unavailable')
                    continue
                raw,e['log_snapshot']=captured
                if load_observation(raw,e['ticket'],partial=True) is not None:
                    if e['identity'] is None:raise RuntimeError(role+' receipt without owned X4')
                    ready.add(role)
            check_cancel()
            if time.monotonic()>=deadline:raise TimeoutError('census deadline')
            if require_load and ready!={'server','client'}:raise RuntimeError('both load/pause receipts required')
            if require_load:
                for role,e in roles.items():
                    if base.load.game_identity(e['proc'],e['started'],game)!=e['identity']:
                        raise RuntimeError(role+' X4 changed after guard')
            check_cancel()
            if time.monotonic()>=deadline:raise TimeoutError('census deadline')
            return ready
        while inspect_context(require_load=False)!={'server','client'}:
            time.sleep(.2)
        inspect_context(require_load=True)
        details=coord.run({'deadline':deadline,'check':lambda:inspect_context(require_load=True)=={'server','client'}})
        inspect_context(require_load=True)
        if type(details) is not dict:raise RuntimeError('completion unconfirmed')
        result.update(success=True,participant=details,witness_artifact_sha256=verified.witness_sha256)
    except coordinator.NoNewRegistryEntry as error:
        no_event=True;result.update(success=False,error=str(error))
    except BaseException as error:
        result.update(success=False,error=str(error) or type(error).__name__)
    finally:
        errors=[];remaining=[];stop_confirmed=True;known=True
        for number in handlers:
            try:signal.signal(number,signal.SIG_IGN)
            except BaseException as error:stop_confirmed=False;errors.append('signal fence: '+type(error).__name__)
        if cancel[0] is not None:result.update(success=False,error='signal '+str(cancel[0]))
        helper_confirmed=stop_confirmed
        if coord is not None:
            try:
                if coord.cleanup_before_owned_processes() is not True:raise RuntimeError('helper cleanup unconfirmed')
            except BaseException as error:helper_confirmed=False;stop_confirmed=False;errors.append('helper cleanup: '+type(error).__name__)
        if compiler_error is not None:
            helper_confirmed=False;stop_confirmed=False;errors.append('compiler cleanup: '+type(compiler_error).__name__)
        for proc,started in (reversed(processes) if helper_confirmed else ()):
            try:
                if started is None:
                    if proc.poll() is None:proc.terminate();proc.wait(timeout=15)
                    known=False;stop_confirmed=False;errors.append('owned launcher identity unavailable')
                else:
                    live=base.snapshot.stop_owned(proc,started)
                    if not isinstance(live,list) or any(type(x) is not int or x<=0 for x in live):raise RuntimeError('invalid cleanup result')
                    remaining.extend(live)
                    if live:stop_confirmed=False;errors.append('owned processes remain')
            except BaseException as error:known=False;stop_confirmed=False;errors.append('owned cleanup: '+type(error).__name__)
        result['owned_processes_remaining']=remaining if helper_confirmed and known else None
        result['owned_cleanup_confirmed']=stop_confirmed
        if errors:result.update(success=False,cleanup_errors=errors)
        if result['success'] or (no_event and not errors and cancel[0] is None):
            try:
                logs={}
                for role,e in roles.items():
                    fid,_,raw=base.stable_read(e['profile']/'engine-output.log',32<<20,collect=True)
                    base.log_continuity(fid,raw,e['log_snapshot']);load_observation(raw,e['ticket'])
                    if (base.stable_read(e['target'],archive.SIZE,collect=False)[:2]!=e['target_digest'] or
                        any(base.stable_read(p,1<<20,collect=False)[:2]!=v for p,v in e['protected'].items())):
                        raise ValueError(role+' final input changed')
                    logs[role]=raw
                if archive.fingerprints(store)!=verified.archive_fingerprints:raise ValueError('archive changed')
                if no_event:
                    if coord.verify_no_event_final(logs) is not True:raise ValueError('no-event final receipts unconfirmed')
                    result['classification']='inconclusive_no_new_registry_entry'
                elif coord.verify_final(logs) is not True:raise ValueError('census final receipts unconfirmed')
            except BaseException as error:result.update(success=False,error='final evidence: '+(str(error) or type(error).__name__))
        if coord is not None:
            try:
                if coord.cleanup_after_owned_processes() is not True:raise RuntimeError('UDP cleanup unconfirmed')
            except BaseException as error:errors.append('UDP cleanup: '+type(error).__name__)
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
        if errors:
            result.pop('classification',None)
            result.update(success=False,cleanup_errors=errors)
        try:(out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        finally:
            for number,handler in handlers.items():
                try:signal.signal(number,handler)
                except BaseException:pass
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--timeout',type=float,default=600);p.add_argument('--window',type=float,default=60)
    p.add_argument('--seed',type=int,default=276944566)
    try:result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error:p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__':sys.exit(main())
