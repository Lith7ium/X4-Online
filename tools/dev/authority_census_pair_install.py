"""Build private load/owner overlays for the census pair test; no X4 launch."""
import math
from pathlib import Path
import re
import shutil

import authority_census_archive_provenance as archive
import authority_sector_read_live as base
import authority_sector_pair_transfer_live as pair_transfer

ROOT=Path(__file__).resolve().parents[2]
_BASE_MD=('authority_checkpoint_marker.xml','authority_ship_registry.xml','authority_identity_fixture.xml')
_COMMON_UI=('authority_checkpoint_marker_probe.lua','authority_registry_resolve_string.lua',
            'authority_job_registry_probe.lua','authority_job_registry_host.lua',
            'authority_job_descriptor_probe.lua','authority_paused_job_descriptor.lua',
            'authority_sector_witness_runtime.lua','authority_census_job_owner.lua',
            'authority_census_job_owner_x4.lua','authority_census_pair_session.lua')
_GLOBALS={'authority_sector_witness_runtime.lua':'X4LAN_SECTOR_WITNESS_RUNTIME',
          'authority_census_job_owner.lua':'X4LAN_CENSUS_JOB_OWNER',
          'authority_census_job_owner_x4.lua':'X4LAN_CENSUS_JOB_OWNER_X4'}


def install(case,profile,ticket,config,nonce,timeout,window):
    role=config.get('role')
    deferred=config.get('defer_source_ack',False)
    if type(deferred) is not bool or (deferred and role!='server'):raise ValueError('invalid deferred source setting')
    if (role not in ('server','client') or config.get('epoch')!=archive.REGISTRY_EPOCH
        or any(not isinstance(config.get(k),str) or not re.fullmatch(r'[0-9a-f]{32}',config[k]) for k in ('lease','attempt'))
        or not re.fullmatch(r'[0-9a-f]{32}',nonce) or type(config.get('port')) is not int or not 1<=config['port']<=65535
        or config['attempt']==config['epoch'] or not math.isfinite(timeout) or not 60<=timeout<=600
        or not math.isfinite(window) or not 1<=window<=180):raise ValueError('invalid census pair config')
    config_path=base.load.install_probe(case,profile,ticket)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md';native=lab/'native'
    md_names=list(_BASE_MD)+['authority_sector_witness_runtime.xml']
    if role=='server':md_names+=['authority_job_ship_events.xml','authority_paused_job_descriptor.xml']
    else:md_names+=['authority_census_job_baseline.xml']
    for name in md_names:
        source=archive.saved_state_script(name) if name in _BASE_MD else ROOT/'tools/dev'/name
        shutil.copyfile(source,md/name)
    for name in _COMMON_UI:
        text=(ROOT/'tools/dev'/name).read_text()
        if name in _GLOBALS:text=pair_transfer.once(text,'return M\n',_GLOBALS[name]+'=M\nreturn M\n')
        (ui/name).write_text(text)
    extra_ui=()
    if deferred:
        extra_ui=('authority_job_delivery.lua',)
        shutil.copyfile(ROOT/'src/authority/lua/job_delivery.lua',ui/extra_ui[0])
    marker=ui/'authority_checkpoint_marker_probe.lua'
    marker.write_text(pair_transfer.once(marker.read_text(),"if phase~='load' or state~='inspect' or type(marker)~='string'",
        "if marker~=cfg.authority_expected_marker or phase~='load' or state~='inspect' or type(marker)~='string'"))
    text=config_path.read_text(encoding='ascii')
    if not text.endswith('}\n'):raise ValueError('unexpected private config')
    text=text[:-2]+(',authority_marker_phase="load",authority_expected_marker="'+archive.MARKER+'",'
        'authority_census_pair=true,authority_census_role="'+role+'",authority_census_epoch="'+config['epoch']+'",'
        'authority_census_attempt="'+config['attempt']+'",authority_census_lease="'+config['lease']+'",'
        'authority_census_nonce="'+nonce+'",authority_census_port='+str(config['port'])+',authority_census_timeout='+
        format(timeout,'.17g')+',authority_census_window='+format(window,'.17g')+
        (',authority_census_deferred_ack=true' if deferred else '')+'}\n')
    config_path.write_text(text,encoding='ascii');config_path.chmod(0o600)
    manifest=lab/'ui.xml';text=manifest.read_text();hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    manifest.write_text(pair_transfer.once(text,hook,''.join('    <file name="ui/'+n+'" />\n' for n in (*extra_ui,*_COMMON_UI))+hook))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text()
    hook="local state='initial';local failed=false\n"
    text=pair_transfer.once(text,hook,hook+'local pause_requested=false;local pause_confirmed=false\n')
    hook=" elseif state=='observing' then\n"
    text=pair_transfer.once(text,hook,hook+'''  if not engine.is_paused() then
   if pause_confirmed then error('pre-attach pause lost') end
   if not pause_requested then pause_requested=true;engine.pause() end
   return
  end
  pause_confirmed=true
  if not X4LAN_AUTHORITY_MARKER_READY() then return end
''')
    owner.write_text(pair_transfer.once(text," if state=='done' then return end\n",
        " if state=='done' then X4LAN_CENSUS_PAIR_TICK();return end\n"))
    compiler=shutil.which('cc')
    if not compiler:raise ValueError('C compiler required')
    native.mkdir(exist_ok=True);lib=native/'x4lan_net.so';pair_transfer.compile_net(compiler,lib)
    if {p.name for p in md.iterdir()}!=set(md_names):raise ValueError('unexpected private census scripts')
    return [config_path,lab/'ui.xml',lab/'content.xml',profile/'content.xml',profile/'config.xml',lib]+[
        md/name for name in md_names]+[ui/name for name in (*extra_ui,*_COMMON_UI,'sha256.lua','client_load_barrier.lua',
        'x4_client_load_engine.lua','authority_download_load_probe.lua')]
