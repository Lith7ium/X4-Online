"""Read-only saved-registry status for the isolated recovery owner."""
import re
import shutil
import os
import stat
from pathlib import Path

from authority.marker_evidence import _parse
import authority_registry_save_evidence as registry

ROOT=Path(__file__).resolve().parents[2]
HEX=re.compile(r'[0-9a-f]{32}\Z')

def checkpoint_status(expected,actual):
    """Bind a first bootstrap save, then require the complete saved mapping."""
    if not isinstance(expected,tuple) or not isinstance(actual,tuple):raise ValueError('invalid registry status')
    if expected and expected[0]=='bootstrap':
        if (len(expected)!=3 or len(actual)!=4 or actual[:3]!=('ready',expected[1],expected[2])):
            raise ValueError('checkpoint registry differs from enrollment')
    elif actual!=expected:
        raise ValueError('checkpoint registry differs from recovered status')
    return actual

def saved_status(checkpoint):
    scripts=cues=vars_count=0
    active_script=active_cue=False
    fields={};state_attributes=[];state_children=0;state_text=False
    def first(path,attrs):
        nonlocal scripts,cues,vars_count,active_script,active_cue,state_children
        if path==['savegame','md','script']:
            active_script=attrs.get('name')=='X4AuthorityShipRegistry';active_cue=False
            scripts+=int(active_script)
        elif path==['savegame','md','script','cue'] and active_script:
            active_cue=attrs.get('name')=='State';cues+=int(active_cue)
            if active_cue:state_attributes.append(dict(attrs))
        elif len(path)>4 and path[:4]==['savegame','md','script','cue'] and active_script and active_cue:
            state_children+=1
            if path==['savegame','md','script','cue','vars']:
                vars_count+=1
            elif path==['savegame','md','script','cue','vars','value']:
                name=attrs.get('name')
                if name in ('$epoch','$last'):
                    if name in fields:raise ValueError('duplicate registry field')
                    fields[name]=dict(attrs)
    def characters(path,value):
        nonlocal state_text
        if active_script and active_cue and len(path)>=4 and path[:4]==['savegame','md','script','cue'] and value.strip():
            state_text=True
    _parse(checkpoint,first,characters=characters)
    if scripts==0 and cues==0:return ('uninitialized',)
    if (scripts,cues,vars_count,state_children)==(1,1,0,0) and not state_text:
        attrs=state_attributes[0]
        if (set(attrs)=={'id','name','state'} and attrs.get('name')=='State' and
                attrs.get('state')=='waiting' and re.fullmatch(r'[1-9][0-9]{0,8}',attrs.get('id',''))):
            return ('uninitialized',)
        raise ValueError('unknown uninitialized registry cue')
    if (scripts,cues,vars_count)!=(1,1,1) or set(fields)!={'$epoch','$last'}:
        raise ValueError('ambiguous saved registry')
    epoch_ref=fields['$epoch'];last=fields['$last']
    if epoch_ref.get('type')!='string' or not re.fullmatch(r'[1-9][0-9]{0,8}',epoch_ref.get('value','')):
        raise ValueError('invalid saved epoch reference')
    if last.get('type')!='integer' or not re.fullmatch(r'[1-9][0-9]{0,8}',last.get('value','')):
        raise ValueError('empty or invalid saved baseline')
    count=int(last['value'])
    if count>registry.MAX_ENTRIES:raise ValueError('saved baseline exceeds limit')
    group=False;matches=[]
    def second(path,attrs):
        nonlocal group
        if path==['savegame','script','refs']:group=attrs.get('type')=='string'
        elif path==['savegame','script','refs','ref'] and group and attrs.get('id')==epoch_ref['value']:
            matches.append(attrs.get('string'))
    _parse(checkpoint,second)
    if len(matches)!=1 or not isinstance(matches[0],str) or not HEX.fullmatch(matches[0]):
        raise ValueError('missing or ambiguous saved epoch')
    evidence=registry.verify(checkpoint,matches[0],count,include_mapping_fingerprint=True)
    return ('ready',matches[0],count,evidence['mapping_sha256'])

def matches_log(path,nonce,marker,status):
    expected=('uninitialized' if status==('uninitialized',) else status[1]+'|'+str(status[2]))
    needle='[X4LAN] AUTH_RECOVERY_REGISTRY '+nonce+'|'+marker+'|'+expected
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size>256*1024*1024:
            raise ValueError('invalid registry log')
        with os.fdopen(fd,'rb') as stream:
            fd=-1;raw=stream.read(256*1024*1024+1);after=os.fstat(stream.fileno())
        if (len(raw)>256*1024*1024 or not raw.endswith(b'\n') or
            (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
            raise ValueError('registry log changed or is incomplete')
        content=raw.decode('utf-8')
    finally:
        if fd>=0:os.close(fd)
    rows=[line.split('[X4LAN] AUTH_RECOVERY_REGISTRY ',1)[1].strip()
          for line in content.splitlines()
          if '[X4LAN] AUTH_RECOVERY_REGISTRY ' in line]
    value=needle.split('[X4LAN] AUTH_RECOVERY_REGISTRY ',1)[1]
    matching=[row for row in rows if row.startswith(nonce+'|'+marker+'|')]
    if matching!=[value]:raise ValueError('registry status receipt missing or ambiguous')
    return True

def enrollment_receipt(path,nonce,epoch,limit):
    if not HEX.fullmatch(nonce) or not HEX.fullmatch(epoch) or type(limit) is not int or not 1<=limit<=200000:
        raise ValueError('invalid enrollment receipt parameters')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size>256*1024*1024:raise ValueError('invalid enrollment log')
        with os.fdopen(fd,'rb') as stream:
            fd=-1;raw=stream.read(256*1024*1024+1);after=os.fstat(stream.fileno())
        if (len(raw)>256*1024*1024 or not raw.endswith(b'\n') or
            (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
            raise ValueError('enrollment log changed or incomplete')
        rows=[line.split('[X4LAN] AUTH_RECOVERY_ENROLL ',1)[1].strip() for line in raw.decode('utf-8').splitlines()
              if '[X4LAN] AUTH_RECOVERY_ENROLL ' in line]
        matches=[row for row in rows if row.startswith(nonce+'|')]
        if len(matches)!=1:raise ValueError('missing or ambiguous enrollment receipt')
        match=re.fullmatch(re.escape(nonce)+r'\|'+re.escape(epoch)+r'\|([1-9][0-9]*)',matches[0])
        if not match or int(match.group(1))>limit:raise ValueError('invalid enrollment receipt')
        return int(match.group(1))
    finally:
        if fd>=0:os.close(fd)

def install(case,nonce,expected,*,enroll=None):
    if not isinstance(nonce,str) or not HEX.fullmatch(nonce):raise ValueError('invalid registry nonce')
    if expected==('uninitialized',):expected_text='uninitialized'
    elif (type(expected) is tuple and len(expected)==4 and expected[0]=='ready' and
          isinstance(expected[1],str) and HEX.fullmatch(expected[1]) and type(expected[2]) is int and 1<=expected[2]<=registry.MAX_ENTRIES and
          isinstance(expected[3],str) and re.fullmatch(r'[0-9a-f]{64}',expected[3])):
        expected_text=expected[1]+'|'+str(expected[2])
    else:raise ValueError('invalid expected registry status')
    if enroll is not None:
        if (expected!=('uninitialized',) or type(enroll) is not dict or set(enroll)!={'epoch','nonce','limit','save_path'} or
            not isinstance(enroll['epoch'],str) or not HEX.fullmatch(enroll['epoch']) or
            not isinstance(enroll['nonce'],str) or not HEX.fullmatch(enroll['nonce']) or enroll['epoch']==enroll['nonce'] or
            type(enroll['limit']) is not int or not 1<=enroll['limit']<=200000 or
            not isinstance(enroll['save_path'],str) or not enroll['save_path'].endswith('/45841/save') or
            not re.fullmatch(r'/[A-Za-z0-9_./-]+',enroll['save_path'])):
            raise ValueError('invalid enrollment setup')
    lab=Path(case)/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    module=ui/'recovery_registry_status.lua';script=md/'authority_ship_registry.xml'
    config=ui/'config.lua';text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'):raise ValueError('invalid recovery config')
    base_config=text[:-2]+',authority_registry_nonce="'+nonce+'",authority_registry_expected="'+expected_text+'"}\n'
    manifest=lab/'ui.xml';text=manifest.read_text()
    hook='    <file name="ui/authority_world_bridge_probe.lua" />\n'
    if text.count(hook)!=1:raise ValueError('invalid recovery manifest')
    base_manifest=text.replace(hook,'    <file name="ui/recovery_registry_status.lua" />\n'+hook)
    probe=ui/'authority_world_bridge_probe.lua';text=probe.read_text()
    hook='local activated=false\n'
    if text.count(hook)!=1:raise ValueError('invalid recovery owner')
    text=text.replace(hook,hook+'local registry_status=nil\n')
    hook=' if not activated then\n'
    if text.count(hook)!=1:raise ValueError('invalid recovery activation')
    add=''' if not registry_status then
  registry_status=assert(X4LAN_RECOVERY_REGISTRY_STATUS.new({nonce=cfg.authority_registry_nonce,expected=cfg.authority_registry_expected,
   clock=GetCurRealTime,paused=function()return C.IsGamePaused()end,
   register=function(f)return RegisterEvent('X4AuthorityShipRegistry.Correlated',f)~=false end,
   issue=function(screen,op,args)return AddUITriggeredEvent(screen,op,args)~=false end,
   log=function(marker,status)DebugError('[X4LAN] AUTH_RECOVERY_REGISTRY '..cfg.authority_registry_nonce..'|'..marker..'|'..status);return true end,
   store=function(marker)return AddUITriggeredEvent('X4AuthorityCheckpointMarker','Store',{marker=marker})~=false end}))
  assert(registry_status:begin())
 end
 assert(registry_status:tick())
 if not registry_status:ready() then return end
'''
    # The first status is after recovery has observed the marker and pause.
    text=text.replace(hook,add+hook)
    hook="    AddUITriggeredEvent('X4AuthorityCheckpointMarker','Store',{marker=marker})\n"
    if text.count(hook)!=1:raise ValueError('invalid marker hook')
    text=text.replace(hook,'    assert(registry_status:begin(marker))\n')
    protected=[module,script]
    if enroll is not None:
        extras=[('src/authority/lua/x4_ship_engine.lua','x4_ship_engine.lua'),
                ('tools/dev/authority_registry_resolve_string.lua','registry_resolve_string.lua'),
                ('src/authority/lua/ship_registry_client.lua','ship_registry_client.lua'),
                ('src/authority/lua/recovery_registry_enroll.lua','recovery_registry_enroll.lua')]
        client=ui/'ship_registry_client.lua'
        contents=(ROOT/'src/authority/lua/ship_registry_client.lua').read_text()
        if not contents.endswith('return M\n'):raise ValueError('invalid registry client')
        updated_client=contents[:-len('return M\n')]+'X4LAN_SHIP_REGISTRY_CLIENT=M\nreturn M\n'
        updated_config=base_config[:-2]+',authority_enroll_epoch="'+enroll['epoch']+'",authority_enroll_nonce="'+enroll['nonce']+\
            '",authority_enroll_limit='+str(enroll['limit'])+',authority_enroll_save_path="'+enroll['save_path']+'"}\n'
        hook='    <file name="ui/recovery_registry_status.lua" />\n'
        if base_manifest.count(hook)!=1:raise ValueError('registry status hook missing')
        updated_manifest=base_manifest.replace(hook,''.join('    <file name="ui/'+name+'" />\n' for _,name in extras)+hook)
        hook='local registry_status=nil\n'
        if text.count(hook)!=1:raise ValueError('registry status state hook missing or duplicated')
        text=text.replace(hook,'local registry_status,registry_handler,registry_enroller=nil,nil,nil\n')
        old="register=function(f)return RegisterEvent('X4AuthorityShipRegistry.Correlated',f)~=false end,"
        new="""register=function(f)
    registry_handler=f
    return RegisterEvent('X4AuthorityShipRegistry.Correlated',function(_,v)
     if registry_enroller and registry_enroller:state()~='done' then assert(registry_enroller:event(v))
     else registry_handler(nil,v) end
    end)~=false
   end,"""
        if text.count(old)!=1:raise ValueError('registry event hook missing')
        text=text.replace(old,new)
        hook=' if not registry_status:ready() then return end\n'
        if text.count(hook)!=1:raise ValueError('registry ready hook missing')
        text=text.replace(hook,hook+''' if not registry_enroller then
  registry_enroller=assert(X4LAN_RECOVERY_REGISTRY_ENROLL.new_x4({epoch=cfg.authority_enroll_epoch,
   nonce=cfg.authority_enroll_nonce,limit=cfg.authority_enroll_limit,expected_save_path=cfg.authority_enroll_save_path,
   complete=function(epoch,count)
    assert(registry_status:expect_bootstrap(epoch,count))
    DebugError('[X4LAN] AUTH_RECOVERY_ENROLL '..cfg.authority_enroll_nonce..'|'..epoch..'|'..count)
    return true
   end}))
  assert(registry_enroller:start())
 end
 if registry_enroller:state()~='done' then
  assert(registry_enroller:tick())
  if registry_enroller:state()~='done' then return end
 end
''')
    # Hook validation above is read-only; filesystem failures below are not
    # transactional and still require the caller to discard the overlay.
    shutil.copyfile(ROOT/'src/authority/lua/recovery_registry_status.lua',module)
    shutil.copyfile(ROOT/'tools/dev/authority_ship_registry.xml',script)
    config.write_text(base_config,encoding='ascii')
    manifest.write_text(base_manifest)
    if enroll is not None:
        for source,name in extras:
            target=ui/name;shutil.copyfile(ROOT/source,target);protected.append(target)
        client.write_text(updated_client)
        config.write_text(updated_config,encoding='ascii')
        manifest.write_text(updated_manifest)
    probe.write_text(text)
    return protected
