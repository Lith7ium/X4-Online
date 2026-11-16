"""Install the optional combined participant/job UI owner in a disposable case.

No process, listener or display is started by this module.
"""
import math
from pathlib import Path
import re
import shutil
import authority_census_archive_provenance as archive
import authority_census_pair_inputs as inputs
import authority_sector_read_live as base
import authority_sector_pair_transfer_live as transfer

ROOT=Path(__file__).resolve().parents[2]
BASE_MD=('authority_checkpoint_marker.xml','authority_ship_registry.xml','authority_identity_fixture.xml')
MODULES=(('tools/dev/authority_checkpoint_marker_probe.lua','authority_checkpoint_marker_probe.lua',None),
 ('tools/dev/authority_registry_resolve_string.lua','authority_registry_resolve_string.lua',None),
 ('tools/dev/authority_multi_create_client.lua','authority_multi_create_client.lua','X4LAN_MULTI_CREATE_CLIENT'),
 ('src/authority/lua/x4_multi_create_inspector.lua','x4_multi_create_inspector.lua','X4LAN_MULTI_CREATE_INSPECTOR'),
 ('src/authority/lua/control_state.lua','authority_control_state.lua',None),
 ('src/authority/lua/x4_control_engine.lua','x4_control_engine.lua',None),
 ('src/authority/lua/job_client_owner.lua','job_client_owner.lua',None),
 ('src/authority/lua/local_udp_module.lua','local_udp_module.lua','X4LAN_LOCAL_UDP_MODULE'),
 ('tools/dev/authority_participant_job_session.lua','authority_participant_job_session.lua',None))

def install(case,profile,ticket,settings,witnesses):
    required={'participant_port','participant_lease','job_port','lease','attempt','epoch','generation','nonce','seed','timeout'}
    if type(settings) is not dict or set(settings) not in (required,required|{'multi_witness'}):raise ValueError('invalid session settings')
    if 'multi_witness' in settings and settings['multi_witness'] is not True:raise ValueError('multi witness must be explicitly enabled')
    multi=settings.get('multi_witness') is True
    for k in ('participant_lease','lease','attempt','epoch','generation','nonce'):
        if type(settings[k]) is not str or not re.fullmatch(r'[0-9a-f]{32}',settings[k]):raise ValueError('invalid token')
    if len({settings[k] for k in ('participant_lease','lease','attempt','epoch','generation','nonce')})!=6 or settings['epoch']!=archive.REGISTRY_EPOCH:
        raise ValueError('non-unique or unexpected context')
    if (any(type(settings[k]) is not int or not 1<=settings[k]<=65535 for k in ('participant_port','job_port')) or
        settings['participant_port']==settings['job_port'] or type(settings['seed']) is not int or not 0<=settings['seed']<=2147483647 or
        type(settings['timeout']) not in (float,int) or not math.isfinite(settings['timeout']) or not 0<settings['timeout']<=30):
        raise ValueError('invalid ports, seed or timeout')
    if type(witnesses) is not dict or not witnesses or len(witnesses)>152:raise ValueError('invalid saved witnesses')
    saved_witnesses=inputs.load_witness()
    if multi and set(witnesses)!={name for name,items in saved_witnesses.items() if items}:
        raise ValueError('complete eligible witness sectors required')
    for name,idx in witnesses.items():
        if type(name) is not str or not re.fullmatch(r'[A-Za-z0-9_]{1,128}',name):raise ValueError('invalid saved witness sector')
        if multi:
            if type(idx) not in (list,tuple) or not idx or tuple(idx)!=saved_witnesses.get(name,()):
                raise ValueError('complete pinned witness candidates required')
            if any(type(v) is not int or not 1<=v<=archive.COUNT for v in idx):raise ValueError('invalid saved witness index')
        else:
            if type(idx) is not int or not 1<=idx<=archive.COUNT or idx not in saved_witnesses.get(name,()):
                raise ValueError('witness not present in pinned saved evidence')
    config=base.load.install_probe(case,profile,ticket)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md';native=lab/'native'
    names=BASE_MD+('authority_multi_create_receiver.xml',)
    for name in names:shutil.copyfile(archive.saved_state_script(name) if name in BASE_MD else ROOT/'tools/dev'/name,md/name)
    for source,target,global_name in MODULES:
        text=(ROOT/source).read_text()
        if global_name:text=transfer.once(text,'return M\n',global_name+'=M\nreturn M\n')
        (ui/target).write_text(text)
    marker=ui/'authority_checkpoint_marker_probe.lua'
    marker.write_text(transfer.once(marker.read_text(),"if phase~='load' or state~='inspect' or type(marker)~='string'",
        "if marker~=cfg.authority_expected_marker or phase~='load' or state~='inspect' or type(marker)~='string'"))
    literal=base.base.lua_literal;text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'):raise ValueError('unexpected config')
    def witness_literal(v):return '{'+','.join(str(i) for i in v)+'}' if multi else str(v)
    ws='{'+','.join('['+literal(k)+']='+witness_literal(v) for k,v in sorted(witnesses.items()))+'}'
    text=text[:-2]+(',authority_marker_phase="load",authority_expected_marker='+literal(archive.MARKER)+
        ',authority_participant_job_session=true,authority_participant_port='+str(settings['participant_port'])+
        ',authority_participant_lease='+literal(settings['participant_lease'])+',authority_job_client_port='+str(settings['job_port'])+
        ''.join(',authority_job_client_'+k+'='+literal(settings[k]) for k in ('lease','attempt','epoch','generation','nonce'))+
        ',authority_job_client_seed='+str(settings['seed'])+',authority_job_client_baseline='+str(archive.COUNT)+
        ',authority_job_client_timeout='+format(settings['timeout'],'.17g')+',authority_job_client_witnesses='+ws+'}\n')
    config.write_text(text,encoding='ascii');config.chmod(0o600)
    manifest=lab/'ui.xml';hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    manifest.write_text(transfer.once(manifest.read_text(),hook,''.join('    <file name="ui/'+target+'" />\n' for _,target,_ in MODULES)+hook))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text()
    hook="local state='initial';local failed=false\n"
    text=transfer.once(text,hook,hook+'local pause_requested=false;local pause_confirmed=false\n')
    hook=" elseif state=='observing' then\n"
    text=transfer.once(text,hook,hook+'''  if not engine.is_paused() then
   if pause_confirmed then error('pre-session pause lost') end
   if not pause_requested then pause_requested=true;engine.pause() end
   return
  end
  pause_confirmed=true
  if not X4LAN_AUTHORITY_MARKER_READY() then return end
''')
    owner.write_text(transfer.once(text," if state=='done' then return end\n",
        " if state=='done' then X4LAN_PARTICIPANT_JOB_TICK();return end\n"))
    compiler=shutil.which('cc')
    if not compiler:raise ValueError('C compiler required')
    native.mkdir(exist_ok=True);lib=native/'x4lan_net.so';transfer.compile_net(compiler,lib)
    if {p.name for p in md.iterdir()}!=set(names):raise ValueError('unexpected private MD scripts')
    return [config,lab/'ui.xml',lab/'content.xml',profile/'content.xml',profile/'config.xml',lib]+[md/name for name in names]+[
        ui/target for _,target,_ in MODULES]+[ui/name for name in ('sha256.lua','client_load_barrier.lua','x4_client_load_engine.lua','authority_download_load_probe.lua')]
