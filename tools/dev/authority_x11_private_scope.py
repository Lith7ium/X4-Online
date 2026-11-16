"""Sampled Linux ownership fence for a private X11 test display; no input."""
import hashlib
import os
from pathlib import Path
import re
import stat

_DISPLAY=re.compile(r':([1-9][0-9]{0,3})(?:\.0)?\Z',re.ASCII)
_FIELDS=frozenset(('display','auth','auth_sha256','private_root','owner_pid','owner_start',
                   'display_leader','display_leader_start','server_pid','server_start','server_exe',
                   'x4_leader','x4_leader_start','x4_pid','x4_start','x4_exe','window'))

def _stat(pid):
    if type(pid) is not int or pid<=1:raise ValueError('invalid PID')
    p=Path('/proc')/str(pid)
    if p.stat().st_uid!=os.geteuid():raise ValueError('foreign process owner')
    fields=(p/'stat').read_text().rsplit(')',1)[1].split()
    return {'ppid':int(fields[1]),'group':int(fields[2]),'start':int(fields[19])}

def _process(pid,start):
    if type(start) is not int or start<=0:raise ValueError('invalid start time')
    row=_stat(pid)
    if row['start']!=start:raise ValueError('process identity changed')
    return row

def _auth(s):
    root=Path(s['private_root']);path=Path(s['auth'])
    if not root.is_absolute() or not path.is_absolute() or root.is_symlink() or path.is_symlink():raise ValueError('unsafe private path')
    realroot=root.resolve(strict=True);realpath=path.resolve(strict=True)
    if not realpath.is_relative_to(realroot) or realpath==realroot:raise ValueError('authority outside private directory')
    r=realroot.stat()
    if not stat.S_ISDIR(r.st_mode) or r.st_uid!=os.geteuid() or r.st_mode&0o077:raise ValueError('unsafe private directory')
    fd=os.open(realpath,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        a=os.fstat(fd)
        if not stat.S_ISREG(a.st_mode) or a.st_uid!=os.geteuid() or a.st_mode&0o077 or not 0<a.st_size<=65536:
            raise ValueError('unsafe authority file')
        data=os.read(fd,65537);b=os.fstat(fd)
        if len(data)!=a.st_size or (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)!=(b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns):
            raise ValueError('authority changed')
        if hashlib.sha256(data).hexdigest()!=s['auth_sha256']:raise ValueError('authority digest changed')
        now=path.lstat()
        if (now.st_dev,now.st_ino)!=(a.st_dev,a.st_ino):raise ValueError('authority path changed')
    finally:os.close(fd)

def _listeners(display,server_pid):
    number=_DISPLAY.fullmatch(display).group(1)
    paths={'/tmp/.X11-unix/X'+number,'@/tmp/.X11-unix/X'+number}
    found=set()
    for row in Path('/proc/net/unix').read_text().splitlines()[1:]:
        fields=row.split()
        if len(fields)>=8 and fields[7] in paths and fields[5]=='01' and int(fields[3],16)&0x10000:
            found.add(fields[6])
    if not found:raise ValueError('private display has no listener')
    sockets=set()
    for fd in (Path('/proc')/str(server_pid)/'fd').iterdir():
        try:
            m=re.fullmatch(r'socket:\[(\d+)\]',os.readlink(fd))
            if m:sockets.add(m.group(1))
        except FileNotFoundError:continue
    if not found<=sockets:raise ValueError('display listener not exclusively bound to owned server')

def verify(s,*,require_x4=True):
    if type(s) is not dict or set(s)!=_FIELDS:raise ValueError('invalid private scope')
    if type(s['display']) is not str or not _DISPLAY.fullmatch(s['display']):raise ValueError('private display required')
    if type(s['window']) is not int or not 1<=s['window']<=0xffffffff:raise ValueError('invalid window')
    if type(s['auth_sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}',s['auth_sha256']):raise ValueError('invalid authority digest')
    for key in ('auth','private_root','x4_exe','server_exe'):
        if type(s[key]) is not str or not Path(s[key]).is_absolute():raise ValueError('absolute path required')
    owner=_process(s['owner_pid'],s['owner_start'])
    display=_process(s['display_leader'],s['display_leader_start'])
    server=_process(s['server_pid'],s['server_start'])
    if display['ppid']!=s['owner_pid'] or display['group']!=s['display_leader'] or server['group']!=s['display_leader'] or server['start']<display['start']:
        raise ValueError('display not owned by supervisor')
    if Path(s['server_exe']).name not in ('Xwayland','Xvfb','Xephyr','Xorg') or not os.path.samefile('/proc/%d/exe'%s['server_pid'],s['server_exe']):
        raise ValueError('private X server executable differs')
    _auth(s);_listeners(s['display'],s['server_pid'])
    if require_x4:
        leader=_process(s['x4_leader'],s['x4_leader_start']);x4=_process(s['x4_pid'],s['x4_start'])
        if leader['ppid']!=s['owner_pid'] or leader['group']!=s['x4_leader'] or x4['group']!=s['x4_leader'] or x4['start']<leader['start']:
            raise ValueError('X4 not owned by supervisor')
        if not os.path.samefile('/proc/%d/exe'%s['x4_pid'],s['x4_exe']):raise ValueError('X4 executable differs')
        raw=(Path('/proc')/str(s['x4_pid'])/'environ').read_bytes().split(b'\0')
        if ('DISPLAY='+s['display']).encode() not in raw:raise ValueError('X4 display differs')
    # Identity checks and socket ownership are sampled; adversarial ABA is not excluded.
    return True
