"""Build a private single-source job overlay; no process or listener starts."""
import math
from pathlib import Path
import re
import shutil
import authority_census_archive_provenance as archive
import authority_sector_read_live as base
import authority_sector_pair_transfer_live as transfer

ROOT=Path(__file__).resolve().parents[2]
BASE_MD=('authority_checkpoint_marker.xml','authority_ship_registry.xml','authority_identity_fixture.xml')
MD=BASE_MD+('authority_job_ship_events.xml','authority_job_descriptor_probe.xml')
UI=(('tools/dev/authority_checkpoint_marker_probe.lua','authority_checkpoint_marker_probe.lua'),
    ('tools/dev/authority_registry_resolve_string.lua','authority_registry_resolve_string.lua'),
    ('tools/dev/authority_job_registry_probe.lua','authority_job_registry_probe.lua'),
    ('tools/dev/authority_job_registry_host.lua','authority_job_registry_host.lua'),
    ('tools/dev/authority_job_descriptor_probe.lua','authority_job_descriptor_probe.lua'),
    ('src/authority/lua/job_delivery.lua','job_delivery.lua'),
    ('src/authority/lua/source_job_ipc.lua','source_job_ipc.lua'),
    ('src/authority/lua/source_single_job_owner.lua','source_single_job_owner.lua'),
    ('src/authority/lua/control_state.lua','authority_control_state.lua'),
    ('src/authority/lua/x4_control_engine.lua','x4_control_engine.lua'),
    ('tools/dev/authority_source_single_job_session.lua','authority_source_single_job_session.lua'))

def install(case,profile,ticket,settings):
    required={'control_port','control_lease','job_port','lease','attempt','epoch','generation','descriptor_request',
              'timeout','host_timeout','window','capacity','baseline'}
    if type(settings) is not dict or set(settings) not in (required,required|{'max_events'},required|{'continuous'}):raise ValueError('invalid source settings')
    if 'continuous' in settings and settings['continuous'] is not True:raise ValueError('continuous must be explicitly enabled')
    if 'max_events' in settings and (type(settings['max_events']) is not int or not 2<=settings['max_events']<=8):raise ValueError('invalid bounded source count')
    keys=('control_lease','lease','attempt','epoch','generation','descriptor_request')
    if any(type(settings[k]) is not str or not re.fullmatch(r'[0-9a-f]{32}',settings[k]) for k in keys):raise ValueError('invalid source token')
    if (settings['epoch']!=archive.REGISTRY_EPOCH or len({settings[k] for k in keys})!=len(keys) or
        ticket['world_epoch'] in {settings[k] for k in keys}):raise ValueError('source token collision or epoch mismatch')
    if (any(type(settings[k]) is not int or not 1<=settings[k]<=65535 for k in ('control_port','job_port')) or
        settings['control_port']==settings['job_port'] or type(settings['baseline']) is not int or settings['baseline']!=archive.COUNT or
        type(settings['capacity']) is not int or not 1<=settings['capacity']<=1024):raise ValueError('invalid source ports or registry')
    for k in ('timeout','host_timeout','window'):
        if type(settings[k]) not in (int,float) or not math.isfinite(settings[k]):raise ValueError('invalid source timing')
    if not (1<=settings['window']<=90 and 0<settings['host_timeout']<=30 and
            settings['window']+20<=settings['timeout']<=120):raise ValueError('invalid source timing')
    config=base.load.install_probe(case,profile,ticket)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md';native=lab/'native'
    for name in MD:shutil.copyfile(archive.saved_state_script(name) if name in BASE_MD else ROOT/'tools/dev'/name,md/name)
    for source,target in UI:shutil.copyfile(ROOT/source,ui/target)
    marker=ui/'authority_checkpoint_marker_probe.lua'
    marker.write_text(transfer.once(marker.read_text(),"if phase~='load' or state~='inspect' or type(marker)~='string'",
        "if marker~=cfg.authority_expected_marker or phase~='load' or state~='inspect' or type(marker)~='string'"))
    literal=base.base.lua_literal;text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'):raise ValueError('unexpected config')
    text=text[:-2]+(',authority_marker_phase="load",authority_expected_marker='+literal(archive.MARKER)+
        ',authority_source_single_job_session=true'+
        (',authority_source_max_events='+str(settings['max_events']) if 'max_events' in settings else '')+
        (',authority_source_continuous=true' if settings.get('continuous') is True else '')+
        ''.join(',authority_source_'+k+'='+literal(settings[k]) for k in keys)+
        ''.join(',authority_source_'+k+'='+format(settings[k],'.17g') for k in ('control_port','job_port','timeout','host_timeout','window','capacity','baseline'))+'}\n')
    config.write_text(text,encoding='ascii');config.chmod(0o600)
    manifest=lab/'ui.xml';hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    manifest.write_text(transfer.once(manifest.read_text(),hook,''.join('    <file name="ui/'+target+'" />\n' for _,target in UI)+hook))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text();hook="local state='initial';local failed=false\n"
    text=transfer.once(text,hook,hook+'local pause_requested=false;local pause_confirmed=false\n')
    hook=" elseif state=='observing' then\n"
    text=transfer.once(text,hook,hook+'''  if not engine.is_paused() then
   if pause_confirmed then error('pre-source pause lost') end
   if not pause_requested then pause_requested=true;engine.pause() end
   return
  end
  pause_confirmed=true
  if not X4LAN_AUTHORITY_MARKER_READY() then return end
''')
    owner.write_text(transfer.once(text," if state=='done' then return end\n",
        " if state=='done' then X4LAN_SOURCE_SINGLE_JOB_TICK();return end\n"))
    compiler=shutil.which('cc')
    if not compiler:raise ValueError('C compiler required')
    native.mkdir(exist_ok=True);lib=native/'x4lan_net.so';transfer.compile_net(compiler,lib)
    if {p.name for p in md.iterdir()}!=set(MD):raise ValueError('unexpected private MD scripts')
    return [config,lab/'ui.xml',lab/'content.xml',profile/'content.xml',profile/'config.xml',lib]+[
        md/name for name in MD]+[ui/target for _,target in UI]+[
        ui/name for name in ('sha256.lua','client_load_barrier.lua','x4_client_load_engine.lua','authority_download_load_probe.lua')]
