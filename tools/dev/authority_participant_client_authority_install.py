"""Private, explicit read-only client-authority overlay; no game launch.

The supervisor must separately inject X4LAN_CLIENT_AUTHORITY_TEST_GRANT, bind
its token/incarnation to the actual admitted peer, and fence owned processes.
"""
import math
from pathlib import Path
import re
import shutil
import authority_participant_job_install as base
ROOT=Path(__file__).resolve().parents[2]
SCRIPTS=(('tools/dev/authority_job_descriptor_probe.lua','authority_job_descriptor_probe.lua'),
 ('src/authority/lua/saved_baseline_source_bootstrap.lua','saved_baseline_source_bootstrap.lua'),
 ('src/authority/lua/source_motion_sampler.lua','source_motion_sampler.lua'),
 ('src/authority/lua/source_motion_ipc.lua','source_motion_ipc.lua'),
 ('src/authority/lua/client_authority_motion_reader.lua','client_authority_motion_reader.lua'),
 ('src/authority/lua/client_authority_motion_session.lua','client_authority_motion_session.lua'))

def install(case,profile,ticket,settings,witnesses,authority):
    keys={'port','lease','attempt','bootstrap_nonce','sampler_nonce','token','incarnation','timeout','interval'}
    if (type(authority) is not dict or set(authority)-{'include_orientation'}!=keys or
        type(authority.get('include_orientation',False)) is not bool):raise ValueError('explicit client authority required')
    names=('lease','attempt','bootstrap_nonce','sampler_nonce','token','incarnation')
    if any(type(authority[k]) is not str or not re.fullmatch(r'[0-9a-f]{32}',authority[k]) for k in names):raise ValueError('invalid authority token')
    vals=[authority[k] for k in names]+[settings.get(k) for k in ('participant_lease','lease','attempt','epoch','generation','nonce')]+[ticket.get('world_epoch')]
    if len(set(vals))!=len(vals) or authority['bootstrap_nonce'][:16]==authority['sampler_nonce'][:16]:raise ValueError('authority tokens overlap')
    if (type(authority['port']) is not int or not 1<=authority['port']<=65535 or authority['port'] in (settings.get('participant_port'),settings.get('job_port')) or
        any(type(authority[k]) not in (int,float) or not math.isfinite(authority[k]) for k in ('timeout','interval')) or
        not 0<authority['timeout']<=30 or not 0<authority['interval']<=60):raise ValueError('invalid authority limits')
    files=base.install(case,profile,ticket,settings,witnesses)
    lab=Path(case)/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    for source,target in SCRIPTS:shutil.copyfile(ROOT/source,ui/target)
    mdfile=md/'authority_job_descriptor_probe.xml';shutil.copyfile(ROOT/'tools/dev/authority_job_descriptor_probe.xml',mdfile)
    manifest=lab/'ui.xml';hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    manifest.write_text(base.transfer.once(manifest.read_text(),hook,''.join('    <file name="ui/'+target+'" />\n' for _,target in SCRIPTS)+hook))
    config=ui/'config.lua';text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'):raise ValueError('unexpected private config')
    literal=base.base.base.lua_literal
    props=','.join(k+'='+literal(authority[k]) for k in names)
    # The external, explicitly injected callback must check the participant's
    # epoch/generation/index/token/incarnation; this overlay invents no grant.
    text=text[:-2]+(',authority_client_authority_test={enabled=true,port='+str(authority['port'])+','+props+
      ',timeout='+format(authority['timeout'],'.17g')+',interval='+format(authority['interval'],'.17g')+
      ',include_orientation='+('true' if authority.get('include_orientation',False) else 'false')+
      ',grant=function(e,g,i,t,n,w) return type(X4LAN_CLIENT_AUTHORITY_TEST_GRANT)=="function" and X4LAN_CLIENT_AUTHORITY_TEST_GRANT(e,g,i,t,n,w)==true end}}\n')
    config.write_text(text,encoding='ascii');config.chmod(0o600)
    return files+[mdfile]+[ui/name for _,name in SCRIPTS]
