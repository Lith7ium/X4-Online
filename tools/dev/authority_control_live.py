#!/usr/bin/env python3
"""Explicit single-X4 pause/save/verify/resume experiment in a fresh private profile.

This reuses linux_snapshot_capture's pinned executable, private case, namespace
and owned-process cleanup. It does not use the lockstep gate. The control signal
is a one-run loopback diagnostic, not the multiplayer network protocol. No normal
profile or save is mounted writable. This script is never run by importing it.
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
from lockstep.launcher import extension
import linux_gate_live as live
import linux_snapshot_capture as snapshot


MARKERS = ('AUTH_CONTROL ARMED', 'AUTH_CONTROL PAUSE confirmed',
           'AUTH_CONTROL SAVE native_event_only', 'AUTH_CONTROL RESUME confirmed',
           'AUTH_CONTROL COMPLETE')


def install_probe(case, port, lease):
    """Replace only the freshly generated, private capture overlay in this case."""
    if type(port) is not int or not 1 <= port <= 65535 or not re.fullmatch(r'[0-9a-f]{32}', lease):
        raise ValueError('invalid private control configuration')
    lab = case / 'extensions/x4_lan_lab'
    if lab.is_symlink() or not lab.is_dir():
        raise ValueError('owned disposable extension missing')
    ui = lab / 'ui'
    for source, target in ((REPO/'src/authority/lua/control_state.lua', 'control_state.lua'),
                           (REPO/'src/authority/lua/x4_control_engine.lua', 'x4_control_engine.lua'),
                           (REPO/'tools/dev/authority_control_probe.lua', 'authority_control_probe.lua')):
        shutil.copyfile(source, ui / target)
    # The original capture snapshot script must never run in this experiment.
    (ui/'native_gate_snapshot.lua').unlink()
    (lab/'md/native_gate_battle.xml').unlink()
    files = [*extension.BASE_UI, 'ui/x4ls_autostart.lua', 'ui/control_state.lua',
             'ui/x4_control_engine.lua', 'ui/authority_control_probe.lua']
    (lab/'ui.xml').write_text(extension.ui_xml(files), encoding='utf-8')
    config = ui/'config.lua'
    config.chmod(0o600)
    config.write_text('X4LAN_CONFIG = {enabled=false, test_profile="45841", '
                      'x4ls_autostart="custom_creative", authority_control_probe=true, '
                      f'authority_control_port={port}, authority_control_lease="{lease}"'+'}\n', encoding='ascii')
    compiler = shutil.which('cc')
    if not compiler:
        raise ValueError('a C compiler is needed for the existing native UDP module')
    target = lab/'native/x4lan_net.so'
    subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                    str(REPO/'src/native/net.c'), '-ldl', '-o', str(target)], check=True, capture_output=True)


class ControlLogWatch:
    """Incrementally retain fixed receipt state, with bounded memory and strict order."""
    TAG = b'[X4LAN] AUTH_CONTROL '
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
                    expected = (MARKERS[self.next_receipt].removeprefix('AUTH_CONTROL ').encode('ascii')
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


def verify_and_commit(profile, store):
    """Verify and seal the one newly created gzip/XML save before authorizing resume."""
    source = profile/'save'/snapshot.SLOT
    if source.is_symlink() or not source.is_file():
        raise ValueError('completed private save is missing')
    checkpoint = store.publish(source)
    if store.get(checkpoint.checkpoint_id) != checkpoint:
        raise ValueError('published checkpoint failed independent readback')
    return checkpoint


def send_verified(sock, peer, lease, checkpoint):
    if not isinstance(lease,str) or not re.fullmatch(r'[0-9a-f]{32}',lease):
        raise ValueError('invalid private control lease')
    if not isinstance(checkpoint, Checkpoint):
        raise ValueError('a verified immutable checkpoint is required before resume')
    if not (isinstance(peer, tuple) and len(peer)==2 and peer[0]=='127.0.0.1'):
        raise ValueError('resume requires the enrolled local process endpoint')
    sock.sendto(('VERIFIED|'+lease).encode('ascii'), peer)


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
        case,profile,binds,lock=snapshot.prepare_case(out,game,home)
        if any(p.name!='steam_autocloud.vdf' for p in (profile/'save').iterdir()):
            raise RuntimeError('new isolated save directory is not empty')
        install_probe(case,sock.getsockname()[1],lease)
        (out/'checkpoints').mkdir(mode=0o700)
        store=CheckpointStore(out/'checkpoints')
        lock_fd,lock_stat=live.create_lock_target(snapshot.LOCK_TARGET,user.pw_uid,user.pw_gid)
        for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
            handlers[number]=signal.signal(number,snapshot.cancel_capture)
        with (out/'process.log').open('wb') as log:
            proc=subprocess.Popen(snapshot.command_for(case,game,binds,lock,args.display,auth,user.pw_name,args.seed),
                                  stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            started=live.start_ticks(proc.pid)
            deadline=time.monotonic()+args.timeout
            peer=checkpoint=None
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
                if receipt[2] and checkpoint is None:
                    checkpoint=verify_and_commit(profile,store)
                    result.update(checkpoint_id=checkpoint.checkpoint_id,sha256=checkpoint.sha256,size=checkpoint.size,
                                  native_save_event=True,file_verified=True)
                if checkpoint is not None and peer is not None and not receipt[4]:
                    if time.monotonic()>=deadline or proc.poll() is not None or live.steam_identity(home,user.pw_uid)!=steam:
                        raise RuntimeError('control ownership expired before resume')
                    send_verified(sock,peer,lease,checkpoint)
                if receipt[4]:
                    if checkpoint is None or peer is None: raise RuntimeError('resume preceded independent verification')
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
