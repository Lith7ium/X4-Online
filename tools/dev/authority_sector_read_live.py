#!/usr/bin/env python3
"""Opt-in single-X4 archived checkpoint read diagnostic; import never launches X4."""
import argparse
import hashlib
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
from authority.checkpoints import CheckpointStore, _read_regular
from authority_marked_admission_evidence import _read_regular as stable_read, EvidenceFileGrowing
import authority_download_load_live as load
import authority_load_live as base
import authority_sector_archive_provenance as archive
import linux_gate_live as live
import linux_snapshot_capture as snapshot

MD=('authority_checkpoint_marker.xml','authority_ship_registry.xml','authority_sector_reference_fixture.xml')
UI=('authority_checkpoint_marker_probe.lua','authority_registry_resolve_string.lua','authority_sector_read_probe.lua')
# Optional experiment-specific checks run under signal fencing before publication.
result_finalizer=None
NUMBER=r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
DONE=re.compile(r'DONE slot=([12]) pilot=(present|absent) order=([\w-]{1,96}) state=(started|critical|other|none) game=('+NUMBER+r') x=('+NUMBER+r') y=('+NUMBER+r') z=('+NUMBER+r')\Z',re.ASCII)


def check_origin_scripts(store,profile):
    origin=store.parent/'server/case'
    original=origin/'home/.config/EgoSoft/X4/45841/content.xml'
    if _read_regular(original,65536)!=_read_regular(profile/'content.xml',65536):
        raise ValueError('archive and private extension lists differ')
    source=origin/'extensions/x4_lan_lab/md'
    for name in MD:
        if _read_regular(source/name,1<<20)!=_read_regular(ROOT/'tools/dev'/name,1<<20):
            raise ValueError('archive and read probe saved-state scripts differ: '+name)


def install(case,profile,ticket,slot):
    if slot not in (1,2): raise ValueError('slot must be 1 or 2')
    config=load.install_probe(case,profile,ticket)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui'
    for name in (*MD,'authority_sector_read_guard.xml'):
        shutil.copyfile(ROOT/'tools/dev'/name,lab/'md'/name)
    for name in UI: shutil.copyfile(ROOT/'tools/dev'/name,ui/name)
    marker=ui/'authority_checkpoint_marker_probe.lua';text=marker.read_text(encoding='utf-8')
    expected="if phase~='load' or state~='inspect' or type(marker)~='string'"
    if text.count(expected)!=1: raise ValueError('unexpected marker check')
    text=text.replace(expected,"if marker~=cfg.authority_expected_marker or phase~='load' or state~='inspect' or type(marker)~='string'")
    marker.write_text(text,encoding='utf-8')
    text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected load config')
    config.write_text(text[:-2]+',authority_marker_phase="load",authority_expected_marker="'+archive.MARKER+
        '",authority_sector_read=true,authority_sector_epoch="'+archive.REGISTRY_EPOCH+'",authority_sector_slot='+str(slot)+
        ',authority_read_save_path='+base.lua_literal(str(profile/'save'))+'}\n',encoding='ascii')
    config.chmod(0o600)
    manifest=lab/'ui.xml';text=manifest.read_text(encoding='utf-8')
    hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    if text.count(hook)!=1: raise ValueError('unexpected load manifest')
    manifest.write_text(text.replace(hook,''.join('    <file name="ui/'+n+'" />\n' for n in UI)+hook),encoding='utf-8')
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text(encoding='utf-8')
    hook="local state='initial';local failed=false\n"
    if text.count(hook)!=1: raise ValueError('unexpected load state')
    text=text.replace(hook,hook+'local sector_pause_requested=false;local sector_gate_started=false\n')
    hook=" elseif state=='observing' then\n"
    if text.count(hook)!=1: raise ValueError('unexpected load callback')
    text=text.replace(hook,hook+'''  if not engine.is_paused() then
   if sector_gate_started then error('sector pause lost') end
   if not sector_pause_requested then sector_pause_requested=true;engine.pause() end
   return
  end
  sector_gate_started=true
  if not X4LAN_AUTHORITY_MARKER_READY() then return end
  if not X4LAN_SECTOR_READ_READY() then return end
''')
    owner.write_text(text,encoding='utf-8')
    if {p.name for p in (lab/'md').iterdir()}!=set((*MD,'authority_sector_read_guard.xml')):
        raise ValueError('unexpected private MD scripts')
    return [config,lab/'ui.xml',lab/'content.xml',profile/'content.xml',profile/'config.xml']+[
        lab/'md'/name for name in (*MD,'authority_sector_read_guard.xml')]+[
        ui/name for name in (*UI,'sha256.lua','client_load_barrier.lua','x4_client_load_engine.lua','authority_download_load_probe.lua')]


def check_log_bytes(raw,ticket,slot,*,partial=False):
    if not raw.endswith(b'\n'):
        if partial: return None
        raise ValueError('incomplete log')
    lines=raw.decode('utf-8').splitlines();tags=(load.TAG.decode(),'[X4LAN] AUTH_MARKER load ','[X4LAN] AUTH_SECTOR_READ ')
    rows=[]
    for line in lines:
        for tag in tags:
            if tag in line: rows.append((tag,line.split(tag,1)[1].strip()))
    expected=['load_requested|'+'|'.join(str(ticket[k]) for k in load.FIELDS),
              'INSPECTED '+archive.MARKER,
              None,
              'pause_observed|'+'|'.join(str(ticket[k]) for k in load.FIELDS)]
    order=[tags[0],tags[1],tags[2],tags[0]]
    if len(rows)>4 or any(row[0]!=order[i] for i,row in enumerate(rows)):
        raise ValueError('duplicated, reordered or fault receipts')
    if any(i<len(rows) and rows[i][1]!=expected[i] for i in (0,1,3)):
        raise ValueError('load or marker mismatch')
    if len(rows)<4:
        if partial: return None
        raise ValueError('missing receipts')
    m=DONE.fullmatch(rows[2][1])
    if not m or int(m[1])!=slot or (m[3]=='none')!=(m[4]=='none'):
        raise ValueError('invalid read receipt')
    numbers=[float(m[i]) for i in range(5,9)]
    if not all(math.isfinite(n) for n in numbers) or numbers[0]<0: raise ValueError('nonfinite read receipt')
    return dict(slot=slot,reported_pilot=m[2],reported_order_id=m[3],reported_order_state=m[4],
                reported_game_time=numbers[0],reported_position=numbers[1:],pause_checked_in_probe=True)


def check_log(path,ticket,slot):
    return check_log_bytes(stable_read(path,32<<20,collect=True)[2],ticket,slot)


def fault_log(raw):
    # Specific probe faults and X4 script tracebacks; stock DebugError logs are
    # also marked ERROR, so rejecting every X4 error line is unsound.
    lowered=raw.lower()
    return any(tag in lowered for tag in (b'[x4lan] auth_download_load error',
        b'[x4lan] auth_marker load error',b'[x4lan] auth_sector_read error',
        b'stack traceback:',b'error while executing the lua script',
        b'error in md cue md.x4authority',b'error in lua script',b'error in md script'))


def log_continuity(file_id,raw,previous):
    if previous is not None:
        old_id,old_size,old_digest=previous
        if file_id[:2]!=old_id or len(raw)<old_size or hashlib.sha256(raw[:old_size]).digest()!=old_digest:
            raise ValueError('log replaced, truncated or previously written bytes changed')
    return file_id[:2],len(raw),hashlib.sha256(raw).digest()


def check_live_prefix(path,previous):
    """Recheck the accepted prefix without waiting for EOF on a growing file."""
    expected_id,size,digest=previous
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or (before.st_dev,before.st_ino)!=expected_id or before.st_size<size:
            raise ValueError('log replaced or truncated during prefix check')
        remaining=size;actual=hashlib.sha256()
        while remaining:
            part=os.read(fd,min(1<<20,remaining))
            if not part: raise ValueError('log truncated during prefix check')
            actual.update(part);remaining-=len(part)
        after=os.fstat(fd)
        if ((after.st_dev,after.st_ino)!=expected_id or after.st_size<size or actual.digest()!=digest):
            raise ValueError('log prefix changed during capture')
    finally:
        os.close(fd)
    current=path.lstat()
    if not stat.S_ISREG(current.st_mode) or (current.st_dev,current.st_ino)!=expected_id:
        raise ValueError('log replaced during prefix check')


def read_live_log(path,previous):
    """Capture a stable log, retrying only an observed append to the same file.

    A growing read is discarded, but first checked against the preceding stable
    prefix. Path/inode replacement and shrinkage are never treated as growth.
    This is sampled evidence, not protection against adversarial ABA changes.
    """
    try:
        file_id,_,raw=stable_read(path,32<<20,collect=True)
        growing=False
    except FileNotFoundError:
        if previous is not None: raise ValueError('log disappeared') from None
        return None
    except EvidenceFileGrowing as error:
        file_id,raw,growing=error.fingerprint,error.partial,True
        if raw is None: raise ValueError('growing log has no captured bytes')
    try:
        current=path.lstat()
    except FileNotFoundError:
        raise ValueError('log disappeared during capture') from None
    if not stat.S_ISREG(current.st_mode) or (current.st_dev,current.st_ino)!=file_id[:2]:
        raise ValueError('log replaced during capture')
    if current.st_size<len(raw):
        raise ValueError('log truncated after capture')
    if previous is not None and file_id[2]<previous[1]:
        raise ValueError('log truncated before capture')
    snapshot=log_continuity(file_id,raw,previous)
    if growing:
        if previous is not None: check_live_prefix(path,previous)
        return None
    return raw,snapshot


def run(args):
    if sys.platform!='linux' or os.geteuid()==0: raise ValueError('unprivileged Linux required')
    out=snapshot.output_path(args.out);store_dir=base.local_directory(args.store)
    if store_dir!=archive.DEFAULT_STORE.resolve(strict=True): raise ValueError('only the recorded archive is supported')
    poll_interval=getattr(args,'poll_interval',.1)
    if (args.slot not in (1,2) or not math.isfinite(args.timeout) or args.timeout<30
            or not 0<=args.seed<=0xffffffff or not math.isfinite(poll_interval) or not .1<=poll_interval<=2):
        raise ValueError('invalid slot, timeout or seed')
    game=args.game.resolve(strict=True)
    if live.sha(game/'X4')!=live.EXE_SHA or not (game/'extensions').is_dir() or not shutil.which('bwrap'):
        raise ValueError('pinned X4 or bubblewrap unavailable')
    if live.x4_executables(): raise ValueError('another X4 process is running')
    if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?',args.display): raise ValueError('local X11 display required')
    auth=Path(os.environ.get('XAUTHORITY',''))
    if not auth.is_file() or not os.access(auth,os.R_OK): raise ValueError('readable XAUTHORITY required')
    auth=auth.resolve(strict=True);user=pwd.getpwuid(os.geteuid());home=Path(user.pw_dir)
    steam=live.steam_identity(home,user.pw_uid)
    before=archive._path_fingerprints(store_dir);origin=archive.verify(store_dir)
    if archive._path_fingerprints(store_dir)!=before: raise ValueError('archive changed after verification')
    out.mkdir(mode=0o700,parents=True,exist_ok=False)
    result={'success':False,'scope':'one isolated Linux X4 read; no admission or gameplay',
            'checkpoint_requested':False,'exact_loaded_file_proven':False,'runtime_save_actor_binding_proven':False,
            'independent_md_reads_proven':False,'continuous_pause_proven':False}
    proc=started=lock_fd=lock_stat=None;handlers={};profile=target=None;protected={};gate_read=gate_write=None
    gate_released=False
    cancellation=[None];log_snapshot=None
    def remember(number,frame): cancellation[0]=cancellation[0] or number
    def check_cancel():
        if cancellation[0] is not None: raise InterruptedError('signal '+str(cancellation[0]))
    try:
        for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP): handlers[number]=signal.signal(number,remember)
        case,profile,binds,lock=snapshot.prepare_case(out,game,home)
        check_origin_scripts(store_dir,profile)
        checkpoint,target=base.stage_checkpoint(CheckpointStore(store_dir),archive.CHECKPOINT_ID,profile)
        if (checkpoint.sha256,checkpoint.size)!=(origin['sha256'],origin['size']) or archive._path_fingerprints(store_dir)!=before:
            raise ValueError('archive changed during staging')
        ticket=dict(world_epoch=secrets.token_hex(16),connection_handle=1,baseline_id=1,load_generation=1,
                    checkpoint_id=checkpoint.checkpoint_id,sha256=checkpoint.sha256,attempt_id=secrets.token_hex(16),slot='save_009')
        protected={p:stable_read(p,1<<20,collect=False)[:2] for p in install(case,profile,ticket,args.slot)}
        target_identity=stable_read(target,origin['size'],collect=False)[:2]
        if target_identity[1]!=origin['sha256']: raise ValueError('staged checkpoint digest mismatch')
        check_origin_scripts(store_dir,profile)
        for name in MD:
            if _read_regular(case/'extensions/x4_lan_lab/md'/name,1<<20)!=_read_regular(store_dir.parent/'server/case/extensions/x4_lan_lab/md'/name,1<<20):
                raise ValueError('staged MD differs from archived MD')
        lock_fd,lock_stat=live.create_lock_target(snapshot.LOCK_TARGET,user.pw_uid,user.pw_gid)
        command=base.readonly_save_command(case,game,binds,lock,args.display,auth,user.pw_name,args.seed,target)
        pos=command.index('--die-with-parent')
        for path in protected:
            command[pos:pos]=['--ro-bind',str(path),str(path)];pos+=3
        if (live.x4_executables() or live.steam_identity(home,user.pw_uid)!=steam or
            stable_read(target,origin['size'],collect=False)[:2]!=target_identity):
            raise RuntimeError('process, Steam identity or staged save changed before launch')
        check_cancel()
        with (out/'process.log').open('wb') as log:
            gate_read,gate_write=os.pipe2(os.O_CLOEXEC)
            proc=subprocess.Popen([sys.executable,str(ROOT/'tools/dev/authority_exec_gate.py'),str(gate_read),*command],
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,pass_fds=(gate_read,))
            os.close(gate_read);gate_read=None
            started=live.start_ticks(proc.pid)
            if proc.poll() is not None or live.start_ticks(proc.pid)!=started: raise RuntimeError('launch gate changed')
            check_cancel()
            if os.write(gate_write,b'G')!=1: raise RuntimeError('launch gate refused')
            gate_released=True
            os.close(gate_write);gate_write=None
            deadline=time.monotonic()+args.timeout;seen=None
            while True:
                check_cancel()
                if time.monotonic()>=deadline: raise TimeoutError('load/read deadline')
                identity=load.game_identity(proc,started,game)
                if identity is not None:
                    if seen is not None and seen!=identity: raise RuntimeError('owned X4 changed')
                    seen=identity
                elif seen is not None: raise RuntimeError('owned X4 disappeared')
                if live.steam_identity(home,user.pw_uid)!=steam: raise RuntimeError('Steam identity changed')
                if any(stable_read(path,1<<20,collect=False)[:2]!=identity for path,identity in protected.items()):
                    raise ValueError('protected configuration changed')
                captured=read_live_log(profile/'engine-output.log',log_snapshot)
                if captured is None: time.sleep(poll_interval);continue
                raw,log_snapshot=captured
                if fault_log(raw): raise RuntimeError('load/read probe reported a fault')
                observed=check_log_bytes(raw,ticket,args.slot,partial=True)
                if observed is not None:
                    if seen is None: raise RuntimeError('receipt without owned X4')
                    check_cancel()
                    if (time.monotonic()>=deadline or load.game_identity(proc,started,game)!=seen or
                        live.steam_identity(home,user.pw_uid)!=steam):
                        raise RuntimeError('identity or deadline changed during final live log check')
                    result.update(observed);result['success']=True;break
                time.sleep(poll_interval)
    except BaseException as error:
        result['error']=str(error) or type(error).__name__
    finally:
        # Never let an individual cleanup failure skip the remaining cleanup.
        cleanup_errors=[];stop_confirmed=proc is None
        def cleanup_error(message,error=None):
            cleanup_errors.append(message+((': '+type(error).__name__) if error is not None else ''))
            result['success']=False
        for number in handlers:
            try: signal.signal(number,signal.SIG_IGN)
            except BaseException as error: cleanup_error('cannot fence cleanup signals',error)
        if cancellation[0] is not None: result.update(success=False,error='signal '+str(cancellation[0]))
        for fd in (gate_read,gate_write):
            if fd is not None:
                try: os.close(fd)
                except BaseException as error: cleanup_error('gate close failed',error)
        if proc is not None:
            try:
                if started is None:
                    # With an unreleased gate the child cannot have executed the launcher.
                    if gate_released: raise RuntimeError('launcher released without identity')
                    if proc.poll() is None: proc.terminate();proc.wait(timeout=15)
                    stop_confirmed=True
                    cleanup_error('owned process identity unavailable')
                else:
                    remaining=snapshot.stop_owned(proc,started)
                    if not isinstance(remaining,list) or any(type(pid) is not int or pid<=0 for pid in remaining):
                        raise RuntimeError('invalid owned cleanup result')
                    result['owned_processes_remaining']=remaining
                    if remaining: cleanup_error('owned processes remain')
                    else: stop_confirmed=True
            except BaseException as error: cleanup_error('owned cleanup failed',error)
        if result['success']:
            try:
                file_id,_,raw=stable_read(profile/'engine-output.log',32<<20,collect=True)
                log_continuity(file_id,raw,log_snapshot)
                if fault_log(raw): raise ValueError('final log faulted')
                if stable_read(target,origin['size'],collect=False)[:2]!=target_identity:
                    raise ValueError('staged save changed')
                if any(stable_read(path,1<<20,collect=False)[:2]!=identity for path,identity in protected.items()):
                    raise ValueError('protected file changed')
                result.update(check_log_bytes(raw,ticket,args.slot))
            except BaseException as error:
                result.update(success=False,error='final validation: '+(str(error) or type(error).__name__))
        if lock_stat is not None:
            if stop_confirmed:
                try: live.release_lock_target(snapshot.LOCK_TARGET,lock_fd,lock_stat)
                except BaseException as error: cleanup_error('lock cleanup failed',error)
            else:
                cleanup_error('lock retained: owned process stop unconfirmed')
                # Retain the lock pathname, but do not leak this process's FD.
                try: os.close(lock_fd)
                except BaseException as error: cleanup_error('lock descriptor close failed',error)
        try:
            if live.steam_identity(home,user.pw_uid)!=steam: result.update(success=False,error='Steam identity changed')
        except BaseException as error: cleanup_error('Steam identity unavailable',error)
        if cleanup_errors: result['cleanup_error']='; '.join(cleanup_errors)
        if result_finalizer is not None:
            was_success=result.get('success') is True
            try:
                result_finalizer(result)
                if type(result.get('success')) is not bool:
                    raise ValueError('finalizer must preserve boolean success')
                if not was_success and result.get('success') is True:
                    raise ValueError('finalizer cannot convert failure to success')
            except BaseException as error:
                result.update(success=False,error='final result check: '+(str(error) or type(error).__name__))
        try:
            (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        finally:
            for number,handler in handlers.items():
                try: signal.signal(number,handler)
                except BaseException: pass
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--slot',type=int,choices=(1,2),required=True);p.add_argument('--timeout',type=float,default=600)
    p.add_argument('--seed',type=int,default=276944566)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__': sys.exit(main())
