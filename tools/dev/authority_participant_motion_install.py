"""Install an opt-in read-only motion bind into the existing private UI owner.

Does not launch X4 or connect a network. Caller owns the profile and sockets.
"""
from pathlib import Path
import math
import re
import shutil
import authority_participant_job_install as base

ROOT=Path(__file__).resolve().parents[2]

def install(case, profile, ticket, settings, witnesses, motion):
    fields={'port','lease','attempt','epoch','generation','nonce','timeout','max_age','max_tracks'}
    if type(motion) is not dict or set(motion) not in (fields,fields|{'saved_baseline'}):raise ValueError('invalid motion settings')
    if 'saved_baseline' in motion and motion['saved_baseline'] is not True:raise ValueError('saved baseline must be explicitly enabled')
    if any(type(motion[k]) is not str or not re.fullmatch(r'[0-9a-f]{32}',motion[k]) for k in ('lease','attempt','epoch','generation','nonce')):
        raise ValueError('invalid motion token')
    if (motion['epoch']!=settings.get('epoch') or motion['generation']!=settings.get('generation') or
        len({motion[k] for k in ('lease','attempt','epoch','generation','nonce')})!=5 or
        any(motion[k] in {settings.get(n) for n in ('participant_lease','lease','attempt','generation','nonce')} for k in ('lease','attempt','nonce'))):
        raise ValueError('motion context conflicts')
    if (type(motion['port']) is not int or not 1<=motion['port']<=65535 or
        motion['port'] in (settings.get('participant_port'),settings.get('job_port')) or
        type(motion['max_tracks']) is not int or not 1<=motion['max_tracks']<=100000 or
        any(type(motion[k]) not in (int,float) or not math.isfinite(motion[k]) or not 0<motion[k]<=30 for k in ('timeout','max_age'))):
        raise ValueError('invalid motion limits')
    files=base.install(case,profile,ticket,settings,witnesses)
    lab=Path(case)/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    scripts=(('src/authority/lua/replica_motion_binding.lua','replica_motion_binding.lua'),
             ('src/authority/lua/motion_client_owner.lua','motion_client_owner.lua'),
             ('src/authority/lua/motion_buffer.lua','motion_buffer.lua'))+(
             (('src/authority/lua/saved_baseline_motion_binding.lua','saved_baseline_motion_binding.lua'),) if motion.get('saved_baseline') else ())
    for source,target in scripts:
        text=(ROOT/source).read_text()
        if target=='motion_buffer.lua':text=base.transfer.once(text,'return M\n','X4LAN_MOTION_BUFFER=M\nreturn M\n')
        (ui/target).write_text(text)
    mdfile=md/'authority_replica_motion_bind.xml';shutil.copyfile(ROOT/'tools/dev/authority_replica_motion_bind.xml',mdfile)
    saved_md=md/'authority_saved_baseline_motion_bind.xml'
    if motion.get('saved_baseline'):shutil.copyfile(ROOT/'tools/dev/authority_saved_baseline_motion_bind.xml',saved_md)
    manifest=lab/'ui.xml';hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    manifest.write_text(base.transfer.once(manifest.read_text(),hook,''.join('    <file name="ui/'+target+'" />\n' for _,target in scripts)+hook))
    config=ui/'config.lua';text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'):raise ValueError('unexpected config')
    literal=base.base.base.lua_literal
    text=text[:-2]+(',authority_motion_client_enabled=true,authority_motion_client_port='+str(motion['port'])+
      ''.join(',authority_motion_client_'+k+'='+literal(motion[k]) for k in ('lease','attempt','epoch','generation','nonce'))+
      ',authority_motion_client_timeout='+format(motion['timeout'],'.17g')+',authority_motion_client_max_age='+format(motion['max_age'],'.17g')+
      ',authority_motion_client_max_tracks='+str(motion['max_tracks'])+
      (',authority_motion_client_saved_enabled=true' if motion.get('saved_baseline') else '')+'}\n')
    config.write_text(text,encoding='ascii');config.chmod(0o600)
    return files+[mdfile]+([saved_md] if motion.get('saved_baseline') else [])+[ui/target for _,target in scripts]
