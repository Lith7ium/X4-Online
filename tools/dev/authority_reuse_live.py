#!/usr/bin/env python3
"""Explicit single-X4 three-cycle same-slot save/reuse experiment in a fresh private profile.

This reuses linux_snapshot_capture's pinned executable, private case, namespace
and owned-process cleanup. It does not use the lockstep gate. The control signal
is a one-run loopback diagnostic, not the multiplayer network protocol. No normal
profile or save is mounted writable. This checks saved bytes and pause/resume,
not loading or multiplayer. This script is never run by importing it.
"""
import argparse
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import json

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(REPO / 'tools/dev'))
from authority.checkpoints import Checkpoint, CheckpointStore
from authority_control_cycle_evidence import CycleEvidence, read_cycle_evidence
from lockstep.launcher import extension
import linux_gate_live as live
import linux_snapshot_capture as snapshot


MARKERS = ('AUTH_REUSE ARMED', *tuple(
    marker for cycle in (1, 2, 3) for marker in (
        f'AUTH_REUSE PAUSE {cycle} confirmed', f'AUTH_REUSE SAVE {cycle} native_event_only',
        f'AUTH_REUSE RESUME {cycle} confirmed')), 'AUTH_REUSE COMPLETE')


def install_probe(case, port, lease, cycle_id):
    """Replace only the freshly generated, private capture overlay in this case."""
    if type(port) is not int or not 1 <= port <= 65535 or not re.fullmatch(r'[0-9a-f]{32}', lease) or not re.fullmatch(r'[0-9a-f]{32}', cycle_id):
        raise ValueError('invalid private control configuration')
    lab = case / 'extensions/x4_lan_lab'
    if lab.is_symlink() or not lab.is_dir():
        raise ValueError('owned disposable extension missing')
    ui = lab / 'ui'
    for source, target in ((REPO/'src/authority/lua/control_state.lua', 'authority_control_state.lua'),
                           (REPO/'src/authority/lua/x4_control_engine.lua', 'x4_control_engine.lua'),
                           (REPO/'tools/dev/authority_reuse_probe.lua', 'authority_reuse_probe.lua')):
        shutil.copyfile(source, ui / target)
    # The original capture snapshot script must never run in this experiment.
    (ui/'native_gate_snapshot.lua').unlink()
    (lab/'md/native_gate_battle.xml').unlink()
    files = [*extension.BASE_UI, 'ui/x4ls_autostart.lua', 'ui/authority_control_state.lua',
             'ui/x4_control_engine.lua', 'ui/authority_reuse_probe.lua']
    (lab/'ui.xml').write_text(extension.ui_xml(files), encoding='utf-8')
    config = ui/'config.lua'
    config.chmod(0o600)
    config.write_text('X4LAN_CONFIG = {enabled=false, test_profile="45841", '
                      'x4ls_autostart="custom_creative", authority_reuse_probe=true, '
                      f'authority_control_port={port}, authority_control_lease="{lease}", authority_cycle_id="{cycle_id}"'+'}\n', encoding='ascii')
    compiler = shutil.which('cc')
    if not compiler:
        raise ValueError('a C compiler is needed for the existing native UDP module')
    target = lab/'native/x4lan_net.so'
    subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                    str(REPO/'src/native/net.c'), '-ldl', '-o', str(target)], check=True, capture_output=True)


class ControlLogWatch:
    """Incrementally retain fixed receipt state, with bounded memory and strict order."""
    TAG = b'[X4LAN] AUTH_REUSE '
    CHUNK = 1 << 20
    MAX_LINE = 65536
    MAX_LOG = 256 << 20

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.identity = None
        self.carry = b''
        self.next_receipt = 0

    @property
    def counts(self):
        return [int(i < self.next_receipt) for i in range(len(MARKERS))]

    def poll(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError:
            return False
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size < self.offset or info.st_size > self.MAX_LOG:
                raise ValueError('control log changed or exceeded its size bound')
            identity = (info.st_dev, info.st_ino)
            if self.identity is not None and self.identity != identity:
                raise ValueError('control log was replaced')
            self.identity = identity
            os.lseek(fd, self.offset, os.SEEK_SET)
            for _ in range(4):
                data = os.read(fd, self.CHUNK)
                if not data:
                    break
                self.offset += len(data)
                lines = (self.carry + data).split(b'\n')
                self.carry = lines.pop()
                if len(self.carry) > self.MAX_LINE:
                    raise ValueError('control log line exceeded its size bound')
                for line in lines:
                    if len(line) > self.MAX_LINE:
                        raise ValueError('control log line exceeded its size bound')
                    if self.TAG not in line:
                        continue
                    row = line.split(self.TAG, 1)[1].strip()
                    if row.startswith(b'ERROR '):
                        raise ValueError('authority control probe reported a failure')
                    expected = (MARKERS[self.next_receipt].removeprefix('AUTH_REUSE ').encode('ascii')
                                if self.next_receipt < len(MARKERS) else None)
                    if row != expected:
                        raise ValueError('duplicate, unexpected or out-of-order authority receipt')
                    self.next_receipt += 1
            size = os.fstat(fd).st_size
            if size > self.MAX_LOG:
                raise ValueError('control log exceeded its size bound')
            return self.offset == size and not self.carry
        finally:
            os.close(fd)


def verify_and_commit(profile, store, cycle, cycle_id, previous_game_time=None):
    """Bind a fully verified checkpoint to its cycle's unique saved title and game time."""
    if cycle not in (1, 2, 3) or not re.fullmatch(r'[0-9a-f]{32}', cycle_id):
        raise ValueError('invalid experiment cycle')
    if (cycle == 1) != (previous_game_time is None):
        raise ValueError('previous cycle evidence required')
    source = profile/'save'/'save_009.xml.gz'
    if source.is_symlink() or not source.is_file():
        raise ValueError('completed private cycle save is missing')
    checkpoint = store.publish(source)
    evidence = read_cycle_evidence(store, checkpoint.checkpoint_id,
                                   f'X4 Authority {cycle_id} {3*cycle-1}',
                                   previous_game_time=previous_game_time)
    return checkpoint, evidence


def send_verified(sock, peer, lease, cycle, cycle_id, checkpoint, evidence):
    if not isinstance(lease,str) or not re.fullmatch(r'[0-9a-f]{32}',lease):
        raise ValueError('invalid private control lease')
    if (cycle not in (1,2,3) or not isinstance(cycle_id,str) or not re.fullmatch(r'[0-9a-f]{32}',cycle_id)
        or not isinstance(checkpoint,Checkpoint) or not isinstance(evidence,CycleEvidence)
        or evidence.checkpoint_id!=checkpoint.checkpoint_id or evidence.sha256!=checkpoint.sha256
        or evidence.size!=checkpoint.size or evidence.save_name!=f'X4 Authority {cycle_id} {3*cycle-1}'):
        raise ValueError('cycle-specific verified immutable checkpoint required')
    if not (isinstance(peer, tuple) and len(peer)==2 and peer[0]=='127.0.0.1'):
        raise ValueError('resume requires the enrolled local process endpoint')
    sock.sendto(('VERIFIED|'+lease+'|'+str(cycle)).encode('ascii'), peer)



def require_authorized_resumes(receipts, authorized):
    for cycle,resume_index in ((1,3),(2,6),(3,9)):
        if receipts[resume_index] and cycle not in authorized:
            raise RuntimeError('resume preceded cycle-specific authorization')

def run(args):
    if sys.platform!='linux' or os.geteuid()==0:
        raise ValueError('run as the unprivileged Linux Steam desktop user')
    out=snapshot.output_path(args.out)
    game=args.game.resolve(strict=True)
    if live.sha(game/'X4')!=live.EXE_SHA or not (game/'extensions').is_dir() or not shutil.which('bwrap'):
        raise ValueError('pinned game or bubblewrap unavailable')
    if live.x4_executables():
        raise ValueError('another X4 process is running')
    if not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?',args.display):
        raise ValueError('a local X11 display is required')
    auth=Path(os.environ.get('XAUTHORITY',''))
    if not auth.is_file() or not os.access(auth,os.R_OK):
        raise ValueError('readable XAUTHORITY required')
    auth=auth.resolve(strict=True)
    if args.timeout<=0 or not 0<=args.seed<=0xffffffff:
        raise ValueError('invalid timeout or seed')
    import pwd
    user=pwd.getpwuid(os.geteuid());home=Path(user.pw_dir)
    steam=live.steam_identity(home,user.pw_uid)
    out.mkdir(mode=0o700,parents=True,exist_ok=False);out.chmod(0o700)
    result={'success':False,'scope':'single isolated Linux X4; no multiplayer', 'steam_before':steam}
    proc=started=lock_fd=lock_stat=None
    handlers={}
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        sock.bind(('127.0.0.1',0));sock.setblocking(False)
        lease=secrets.token_hex(16)
        cycle_id=secrets.token_hex(16)
        case,profile,binds,lock=snapshot.prepare_case(out,game,home)
        if any(p.name!='steam_autocloud.vdf' for p in (profile/'save').iterdir()):
            raise RuntimeError('new isolated save directory is not empty')
        install_probe(case,sock.getsockname()[1],lease,cycle_id)
        (out/'checkpoints').mkdir(mode=0o700)
        stores={}
        for cycle in (1,2,3):
            directory=out/'checkpoints'/f'cycle-{cycle}'
            directory.mkdir(mode=0o700)
            stores[cycle]=CheckpointStore(directory)
        lock_fd,lock_stat=live.create_lock_target(snapshot.LOCK_TARGET,user.pw_uid,user.pw_gid)
        for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
            handlers[number]=signal.signal(number,snapshot.cancel_capture)
        with (out/'process.log').open('wb') as log:
            proc=subprocess.Popen(snapshot.command_for(case,game,binds,lock,args.display,auth,user.pw_name,args.seed),
                                  stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            started=live.start_ticks(proc.pid)
            deadline=time.monotonic()+args.timeout
            peer=None
            checkpoints={}
            evidences={}
            authorized=set()
            watch=ControlLogWatch(profile/'engine-output.log')
            while True:
                if time.monotonic()>=deadline: raise TimeoutError('control experiment timed out')
                if proc.poll() is not None: raise RuntimeError('owned X4 exited before confirmation')
                if live.steam_identity(home,user.pw_uid)!=steam: raise RuntimeError('Steam identity changed')
                try:
                    while True:
                        data,address=sock.recvfrom(513)
                        if data==('HELLO|'+lease).encode('ascii') and address[0]=='127.0.0.1':
                            if peer is not None and peer!=address: raise RuntimeError('control endpoint changed')
                            peer=address
                except BlockingIOError:
                    pass
                caught_up=watch.poll()
                receipt=watch.counts
                if not caught_up:
                    time.sleep(.1);continue
                require_authorized_resumes(receipt,authorized)
                for cycle,save_index in ((1,2),(2,5),(3,8)):
                    if receipt[save_index] and cycle not in checkpoints:
                        if cycle>1 and cycle-1 not in evidences:
                            raise RuntimeError('cycle preceded previous verification')
                        checkpoint,evidence=verify_and_commit(
                            profile,stores[cycle],cycle,cycle_id,
                            evidences[cycle-1].game_time if cycle>1 else None)
                        checkpoints[cycle]=checkpoint
                        evidences[cycle]=evidence
                        result.setdefault('cycles',[]).append({
                            'cycle':cycle,'checkpoint_id':checkpoint.checkpoint_id,
                            'sha256':checkpoint.sha256,'size':checkpoint.size,
                            'game_time':str(evidence.game_time),'file_verified':True})
                for cycle,resume_index in ((1,3),(2,6),(3,9)):
                    if cycle in checkpoints and peer is not None and not receipt[resume_index]:
                        if time.monotonic()>=deadline or proc.poll() is not None or live.steam_identity(home,user.pw_uid)!=steam:
                            raise RuntimeError('control ownership expired before resume')
                        send_verified(sock,peer,lease,cycle,cycle_id,checkpoints[cycle],evidences[cycle])
                        authorized.add(cycle)
                if receipt[10]:
                    if set(checkpoints)!={1,2,3} or peer is None:
                        raise RuntimeError('resume preceded independent cycle verification')
                    result['success']=True;result['resume_confirmed']=True
                    break
                time.sleep(.1)
    except (Exception,KeyboardInterrupt) as error:
        result['error']=str(error)
    finally:
        sock.close()
        if proc is not None and started is None and proc.poll() is None:
            try:
                proc.terminate();proc.wait(timeout=15)
            except (OSError,subprocess.TimeoutExpired):
                result.update(success=False,cleanup_error='unidentified owned launcher cleanup failed')
        if started is not None:
            try:
                remaining=snapshot.stop_owned(proc,started)
                result['owned_processes_remaining']=remaining
                if remaining: result.update(success=False,cleanup_error='owned process group remains')
            except (OSError,subprocess.TimeoutExpired):
                result.update(success=False,cleanup_error='owned process cleanup failed')
        if result['success']:
            try:
                while True:
                    previous_offset=watch.offset
                    if watch.poll(): break
                    if watch.offset==previous_offset: raise ValueError('incomplete final log line')
                if watch.counts != [1]*len(MARKERS):
                    raise ValueError('incomplete final control receipt')
            except (OSError,ValueError):
                result.update(success=False,error='final control receipt invalid')
        if lock_stat is not None:
            try: live.release_lock_target(snapshot.LOCK_TARGET,lock_fd,lock_stat)
            except (OSError,RuntimeError): result.update(success=False,cleanup_error='lock cleanup failed')
        for number,handler in handlers.items(): signal.signal(number,handler)
        try: result['steam_after']=live.steam_identity(home,user.pw_uid)
        except (OSError,ValueError,RuntimeError): result['steam_after']=None
        if result['steam_after']!=steam: result.update(success=False,error='Steam identity changed')
        # Retain the verified save and private evidence; do not leave a live lease.
        config=out/'case/extensions/x4_lan_lab/ui/config.lua'
        if config.is_file():
            try:
                text=config.read_text(encoding='ascii')
                redacted,count=re.subn(r'authority_control_lease="[0-9a-f]{32}"',
                                       'authority_control_lease="redacted"',text)
                if 'authority_control_lease' in text and count!=1:
                    raise ValueError('private control configuration malformed')
                config.write_text(redacted,encoding='ascii')
            except (OSError,UnicodeError,ValueError):
                result.update(success=False,cleanup_error='private control lease cleanup failed')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--display',required=True)
    parser.add_argument('--timeout',type=float,default=600)
    parser.add_argument('--seed',type=int,default=276944566)
    args=parser.parse_args(argv)
    try: result=run(args)
    except (OSError,ValueError,RuntimeError) as error: parser.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if result['success'] else 1


if __name__=='__main__':
    sys.exit(main())
