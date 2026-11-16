"""Install an isolated paused witness diagnostic into a recovery probe."""
import os
import re
import shutil
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEX = re.compile(r'[0-9a-f]{32}\Z')


def install(case, nonce, epoch, count, phase, *, allow_resume=False):
    if (not isinstance(nonce,str) or not HEX.fullmatch(nonce) or
            not isinstance(epoch,str) or not HEX.fullmatch(epoch) or nonce == epoch or
            type(count) is not int or not 1 <= count <= 200000 or phase not in ('create','verify') or
            type(allow_resume) is not bool or (allow_resume and phase!='verify')):
        raise ValueError('invalid witness diagnostic setup')
    lab=Path(case)/'extensions/x4_lan_lab'; ui=lab/'ui'; md=lab/'md'
    script=md/'authority_registry_witness.xml'; module=ui/'recovery_registry_witness.lua'
    if script.exists() or script.is_symlink() or module.exists() or module.is_symlink():
        raise ValueError('witness diagnostic already installed')
    manifest=lab/'ui.xml'; data=manifest.read_text()
    hook='    <file name="ui/recovery_registry_status.lua" />\n'
    if data.count(hook)!=1:raise ValueError('missing witness manifest hook')
    updated_manifest=data.replace(hook,'    <file name="ui/recovery_registry_witness.lua" />\n'+hook)
    probe=ui/'authority_world_bridge_probe.lua'; data=probe.read_text()
    hook='local registry_status=nil\n'
    if data.count(hook)!=1:raise ValueError('missing witness owner state')
    data=data.replace(hook,hook+'local registry_witness=nil\n')
    hook=' if not registry_status:ready() then return end\n'
    if data.count(hook)!=1:raise ValueError('missing witness registry guard')
    config=''' if not registry_witness then
  registry_witness=assert(X4LAN_RECOVERY_REGISTRY_WITNESS.new({enabled=true,epoch='%s',nonce='%s',count=%d,phase='%s',
   clock=GetCurRealTime,paused=function()return C.IsGamePaused()end,
   register=function(f)return RegisterEvent('X4AuthorityRegistryWitness.Result',f)~=false end,
   issue=function(screen,op,args)return AddUITriggeredEvent(screen,op,args)~=false end,
   fault=function(phase,index,reason)
    DebugError('[X4LAN] AUTH_RECOVERY_WITNESS_ERROR '..phase..'|'..index..'|'..reason)
   end,
   complete=function(epoch,count,phase)
    DebugError('[X4LAN] AUTH_RECOVERY_WITNESS '..'%s'..'|'..epoch..'|'..count..'|'..phase..'|sealed');return true
   end}))
  assert(registry_witness:start())
 end
''' % (epoch,nonce,count,phase,nonce)
    if allow_resume:
        # Only the private join proceeds after its completed paused check.
        # A later event changes done to failed and is checked on the next frame.
        config += ''' if registry_witness:state()~='done' then
  assert(registry_witness:tick())
  if registry_witness:state()~='done' then return end
 end
'''
    else:
        config += ''' assert(registry_witness:tick())
 if registry_witness:state()~='done' then return end
'''
    updated_probe=data.replace(hook,hook+config)
    # Validate every hook before touching the caller-owned isolated overlay.
    shutil.copyfile(ROOT/'tools/dev/authority_registry_witness.xml',script)
    shutil.copyfile(ROOT/'src/authority/lua/recovery_registry_witness.lua',module)
    manifest.write_text(updated_manifest)
    probe.write_text(updated_probe)
    return [module,script]


class ErrorWatch:
    """Incrementally fence an owned, append-only X4 log on known failures."""
    TAGS=(b'[X4LAN] AUTH_WORLD_BRIDGE ERROR ',
          b'[X4LAN] AUTH_RECOVERY_WITNESS_ERROR ',
          b'[X4LAN] AUTH_RECOVERED_SOURCE ERROR ',
          b'Error while executing onEvent script for event: X4AuthorityRegistryWitness.Result.')
    LIMIT=256*1024*1024
    def __init__(self,path):
        self.path=Path(path);self.identity=None;self.offset=0;self.tail=b''
    def poll(self):
        try:fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        except FileNotFoundError:
            if self.identity is None:return
            raise ValueError('witness log disappeared')
        try:
            before=os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size>self.LIMIT:
                raise ValueError('invalid witness log')
            identity=(before.st_dev,before.st_ino)
            if self.identity is not None and (identity!=self.identity or before.st_size<self.offset):
                raise ValueError('witness log replaced or truncated')
            self.identity=identity
            while self.offset<before.st_size:
                chunk=os.pread(fd,min(65536,before.st_size-self.offset),self.offset)
                if not chunk:raise ValueError('witness log changed while reading')
                self.offset+=len(chunk);data=self.tail+chunk
                if any(tag in data for tag in self.TAGS):
                    raise ValueError('witness diagnostic reported a bridge or event error')
                self.tail=data[-(max(map(len,self.TAGS))-1):]
            after=os.fstat(fd)
            if (after.st_dev,after.st_ino)!=(before.st_dev,before.st_ino) or after.st_size<before.st_size:
                raise ValueError('witness log changed while reading')
        finally:os.close(fd)


def matches_log(path, nonce, epoch, count, phase):
    # Use the existing bounded, no-symlink, stable log reader.
    import authority_recovered_loopback_server as owner
    if not HEX.fullmatch(nonce) or not HEX.fullmatch(epoch) or type(count) is not int or not 1 <= count <= 200000 or phase not in ('create','verify'):
        raise ValueError('invalid witness receipt request')
    raw=owner.read_evidence(path,256*1024*1024)
    if not raw.endswith(b'\n'):raise ValueError('incomplete witness log')
    if any(tag in raw for tag in ErrorWatch.TAGS):
        raise ValueError('witness diagnostic reported a bridge or event error')
    tag=b'[X4LAN] AUTH_RECOVERY_WITNESS '
    rows=[line.split(tag,1)[1].strip().decode('ascii') for line in raw.splitlines() if tag in line]
    expected=f'{nonce}|{epoch}|{count}|{phase}|sealed'
    if [r for r in rows if r.startswith(nonce+'|')] != [expected]:raise ValueError('missing or ambiguous witness receipt')
    return True
