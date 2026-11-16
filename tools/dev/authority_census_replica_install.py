"""Private client-only replica overlay on the existing census installer."""
from pathlib import Path
import shutil

import authority_census_pair_install as base
import authority_sector_pair_transfer_live as pair

ROOT=Path(__file__).resolve().parents[2]
_BASE_MD=base._BASE_MD
_EXTRA_MD=('authority_census_replica_receiver.xml','authority_census_replica_inspect.xml')
_EXTRA_UI=(('authority_census_replica_client.lua','X4LAN_CENSUS_REPLICA_CLIENT'),
           ('authority_census_replica_client_x4.lua','X4LAN_CENSUS_REPLICA_CLIENT_X4'),
           ('authority_census_replica_udp.lua','X4LAN_CENSUS_REPLICA_UDP'))

def install(case,profile,ticket,config,nonce,timeout,window):
    protected=base.install(case,profile,ticket,config,nonce,timeout,window)
    if config['role']=='server':return protected
    if config['role']!='client':raise ValueError('unexpected role')
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    files=[]
    for name in _EXTRA_MD:
        target=md/name
        if target.exists():raise ValueError('replica MD already exists')
        shutil.copyfile(ROOT/'tools/dev'/name,target);files.append(target)
    target=ui/'x4_ship_engine.lua'
    if target.exists():raise ValueError('replica engine already exists')
    shutil.copyfile(ROOT/'src/authority/lua/x4_ship_engine.lua',target);files.append(target)
    for name,global_name in _EXTRA_UI:
        target=ui/name
        if target.exists():raise ValueError('replica UI already exists')
        text=(ROOT/'tools/dev'/name).read_text()
        target.write_text(pair.once(text,'return M\n',global_name+'=M\nreturn M\n'));files.append(target)
    session=ui/'authority_census_pair_session.lua'
    session.write_text((ROOT/'tools/dev/authority_census_replica_session.lua').read_text())
    manifest=lab/'ui.xml';text=manifest.read_text()
    hook='    <file name="ui/authority_census_pair_session.lua" />\n'
    prefix=''.join('    <file name="ui/'+n+'" />\n' for n in ('x4_ship_engine.lua',*(n for n,_ in _EXTRA_UI)))
    manifest.write_text(pair.once(text,hook,prefix+hook))
    expected=set((*_BASE_MD,'authority_sector_witness_runtime.xml','authority_census_job_baseline.xml',*_EXTRA_MD))
    if {p.name for p in md.iterdir()}!=expected:raise ValueError('unexpected client MD scripts')
    return protected+files
