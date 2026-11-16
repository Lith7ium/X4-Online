"""Add a once-only client motion probe to an owned private recovery overlay.

No game, helper, listener or socket is started. The caller owns the fourth UDP
FD handoff, all process/checkpoint/STOP fences, final log checks and redaction.
This is not yet wired into the recovered-server supervisor.
"""
import math
import os
from pathlib import Path
import re
import stat
import authority_load_live as load

ROOT=Path(__file__).resolve().parents[2]
HEX=re.compile(r'[0-9a-f]{32}\Z')
MODULES=(
 ('tools/dev/authority_registry_resolve_string.lua','authority_registry_resolve_string.lua'),
 ('src/authority/lua/replica_motion_binding.lua','replica_motion_binding.lua'),
 ('src/authority/lua/saved_baseline_motion_binding.lua','saved_baseline_motion_binding.lua'),
 ('src/authority/lua/motion_buffer.lua','motion_buffer.lua'),
 ('src/authority/lua/client_motion_event_router.lua','client_motion_event_router.lua'),
 ('src/authority/lua/motion_client_owner.lua','motion_client_owner.lua'),
 ('tools/dev/authority_recovered_client_motion.lua','authority_recovered_client_motion.lua'),
)
MD=('authority_saved_baseline_motion_bind.xml','authority_replica_motion_bind.xml')
SECRET_FIELDS=('lease','attempt','generation','nonce','router_generation')


class Installation:
    """Protected file set and post-cleanup config redaction; caller fences X4."""
    def __init__(self,paths,config,settings):
        self.paths=tuple(paths);self.config=config;self.secrets={k:settings[k] for k in SECRET_FIELDS}
        st=config.lstat();self.identity=(st.st_dev,st.st_ino)
    def redact(self):
        # Call only after owned X4 has stopped and final input evidence passed.
        fd=os.open(self.config,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            st=os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or (st.st_dev,st.st_ino)!=self.identity or st.st_size>65536:
                raise ValueError('client motion config changed before redaction')
            chunks=[];remaining=st.st_size
            while remaining:
                chunk=os.read(fd,remaining)
                if not chunk:raise ValueError('incomplete client motion config read')
                chunks.append(chunk);remaining-=len(chunk)
            after=os.fstat(fd);path_st=self.config.lstat()
            if ((after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=
                (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns) or
                (path_st.st_dev,path_st.st_ino)!=(st.st_dev,st.st_ino) or not stat.S_ISREG(path_st.st_mode)):
                raise ValueError('client motion config changed during redaction')
            text=b''.join(chunks).decode('ascii')
            for k,v in self.secrets.items():
                original='authority_client_motion_'+k+'="'+v+'"'
                if text.count(original)!=1:raise ValueError('client motion secret missing or repeated')
                text=text.replace(original,'authority_client_motion_'+k+'="redacted"')
            data=text.encode('ascii');os.lseek(fd,0,os.SEEK_SET);written=0
            while written<len(data):
                n=os.write(fd,data[written:])
                if n<=0:raise OSError('short config redaction')
                written+=n
            os.ftruncate(fd,len(data))
        finally:os.close(fd)


def install(case,profile,status,settings):
    """Extend existing disposable client after load/control/registry installation."""
    if (type(status) is not tuple or len(status)!=4 or status[0]!='ready' or
        type(status[1]) is not str or not HEX.fullmatch(status[1]) or
        type(status[2]) is not int or not 1<=status[2]<=200000 or
        type(status[3]) is not str or not re.fullmatch(r'[0-9a-f]{64}',status[3])):
        raise ValueError('observed saved registry required')
    fields={'port','lease','attempt','generation','nonce','router_generation','timeout'}
    if type(settings) is not dict or set(settings) not in (fields|{'index'},fields|{'indices'}):
        raise ValueError('invalid client motion settings')
    indices=[settings['index']] if 'index' in settings else settings['indices']
    if (type(indices) is not list or not 1<=len(indices)<=32 or
        any(type(n) is not int or not 1<=n<=status[2] for n in indices) or len(set(indices))!=len(indices)):
        raise ValueError('invalid client motion indices')
    if (type(settings['port']) is not int or not 1<=settings['port']<=65535 or
        type(settings['timeout']) not in (int,float) or not math.isfinite(settings['timeout']) or
        not 0<settings['timeout']<=30):raise ValueError('invalid client motion bounds')
    tokens=[settings[k] for k in SECRET_FIELDS]
    if any(type(x) is not str or not HEX.fullmatch(x) for x in tokens) or len(set(tokens+[status[1]]))!=6:
        raise ValueError('invalid or colliding client motion tokens')
    case,profile=Path(case),Path(profile)
    if (case.is_symlink() or profile.is_symlink() or not profile.resolve().is_relative_to(case.resolve()) or
        profile.name!='45841' or (profile/'save').is_symlink() or not (profile/'save').is_dir()):
        raise ValueError('private 45841 profile required')
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    if any(p.is_symlink() or not p.is_dir() for p in (lab,ui,md)):
        raise ValueError('invalid client extension')
    config,manifest=ui/'config.lua',lab/'ui.xml'
    control,loader=ui/'authority_two_x4_participant_probe.lua',ui/'authority_download_load_probe.lua'
    required=(config,manifest,control,loader,md/'authority_ship_registry.xml',ui/'recovery_registry_status.lua')
    if any(p.is_symlink() or not p.is_file() for p in required):raise ValueError('client load/control/registry owner unavailable')
    cfg=config.read_text(encoding='ascii');mf=manifest.read_text(encoding='utf-8')
    ctl=control.read_text(encoding='utf-8');load_text=loader.read_text(encoding='utf-8')
    if not cfg.endswith('}\n') or re.search(r'\bauthority_client_motion_[A-Za-z0-9_]+\s*=',cfg):
        raise ValueError('invalid or already extended client config')
    path='authority_load_save_path='+load.lua_literal(str(profile/'save'))
    if cfg.count('authority_load_save_path=')!=1 or not re.search(re.escape(path)+r'(?=,|})',cfg):
        raise ValueError('client save path differs from private profile')
    port=re.findall(r'authority_participant_port=([0-9]+)',cfg)
    old_tokens=re.findall(r'authority_participant_lease="([0-9a-f]{32})"',cfg)
    epochs=re.findall(r'world_epoch="([0-9a-f]{32})"',cfg)
    claims=re.findall(r'attempt_id="([0-9a-f]{32})"',cfg)
    if (len(port)!=1 or int(port[0])==settings['port'] or len(old_tokens)!=1 or len(epochs)!=1 or len(claims)!=1 or
        len(set(tokens+[status[1],old_tokens[0],epochs[0],claims[0]]))!=9):
        raise ValueError('client motion context overlaps existing control')
    marker="expected='"+status[1]+'|'+str(status[2])+"'"
    if load_text.count(marker)!=1 or load_text.count('if not registry_status:ready() then return end')!=1:
        raise ValueError('client registry status differs')
    manifest_hook='    <file name="ui/authority_two_x4_participant_probe.lua" />\n'
    control_hook=' assert(state:on_update())\n'
    local_hook='local net,state,engine,next_hello,failed=nil,nil,nil,0,false\n'
    validity_hook=' if not ffi.C.IsPlayerValid() then return end\n'
    if (mf.count(manifest_hook)!=1 or ctl.count(control_hook)!=1 or ctl.count(local_hook)!=1 or ctl.count(validity_hook)!=1 or
        ctl.count("SetScript('onUpdate'")!=1 or load_text.count("SetScript('onUpdate'")!=1 or
        'X4LAN_RECOVERED_CLIENT_LOAD_READY' in load_text):
        raise ValueError('client owner hooks missing or ambiguous')
    files=[ui/name for _,name in MODULES]+[md/name for name in MD]
    if any(p.exists() or p.is_symlink() for p in files):raise ValueError('client motion overlay would overwrite files')
    for (source,_),target in zip(MODULES,files):
        data=(ROOT/source).read_bytes()
        if target.name=='motion_buffer.lua':
            if data.count(b'return M\n')!=1:raise ValueError('unexpected motion buffer module')
            data=data.replace(b'return M\n',b'X4LAN_MOTION_BUFFER=M\nreturn M\n')
        with target.open('xb') as out:out.write(data)
    for name,target in zip(MD,files[len(MODULES):]):
        with target.open('xb') as out:out.write((ROOT/'tools/dev'/name).read_bytes())
    manifest.write_text(mf.replace(manifest_hook,''.join('    <file name="ui/'+name+'" />\n' for _,name in MODULES)+manifest_hook),encoding='utf-8')
    config_add=',authority_client_motion_enabled=true,authority_client_motion_epoch="'+status[1]+'",authority_client_motion_baseline='+str(status[2])
    config_add+=',authority_client_motion_port='+str(settings['port'])
    if 'index' in settings:config_add+=',authority_client_motion_index='+str(settings['index'])
    else:config_add+=',authority_client_motion_indices={'+','.join(map(str,indices))+'}'
    config_add+=',authority_client_motion_timeout='+format(settings['timeout'],'.17g')
    for name in SECRET_FIELDS:config_add+=',authority_client_motion_'+name+'="'+settings[name]+'"'
    config.write_text(cfg[:-2]+config_add+'}\n',encoding='ascii');config.chmod(0o600)
    loader.write_text(load_text+"\nfunction X4LAN_RECOVERED_CLIENT_LOAD_READY() return state=='done' and not failed end\n",encoding='utf-8')
    code=''' if cfg.authority_client_motion_enabled then
  if not client_motion and X4LAN_RECOVERED_CLIENT_LOAD_READY() and not ffi.C.IsGamePaused() then
   client_motion=assert(X4LAN_RECOVERED_CLIENT_MOTION.new_x4({enabled=true,port=cfg.authority_client_motion_port,
    epoch=cfg.authority_client_motion_epoch,baseline=cfg.authority_client_motion_baseline,index=cfg.authority_client_motion_index,
    indices=cfg.authority_client_motion_indices,
    lease=cfg.authority_client_motion_lease,attempt=cfg.authority_client_motion_attempt,generation=cfg.authority_client_motion_generation,
    nonce=cfg.authority_client_motion_nonce,router_generation=cfg.authority_client_motion_router_generation,
    timeout=cfg.authority_client_motion_timeout,expected_save_path=cfg.authority_load_save_path}))
  end
  if client_motion then assert(client_motion:tick())end
 end
'''
    ctl=ctl.replace(local_hook,local_hook+'ffi.cdef[[bool IsGamePaused(void);]]\nlocal client_motion=nil\n')
    ctl=ctl.replace(validity_hook," if not ffi.C.IsPlayerValid() then if client_motion then error('client motion player lost') end;return end\n")
    control.write_text(ctl.replace(control_hook,control_hook+code),encoding='utf-8')
    return Installation([config,manifest,control,loader,*files],config,settings)
