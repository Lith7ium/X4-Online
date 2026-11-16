"""Private opt-in paused-frame handoff for the client-to-server experiment.

This installs existing diagnostic code only; it starts no process and does not
prove a shared checkpoint, equivalent coordinate frames, or collision clearance.
The caller owns all paths, lifecycle, nonce freshness and post-observation fences.
"""
from pathlib import Path
import re
import shutil
import authority_census_archive_provenance as archive
import authority_participant_motion_install as motion
import authority_saved_frame_compare as frame

ROOT=Path(__file__).resolve().parents[2]
_TOKEN=re.compile(r'[0-9a-f]{32}\Z')

def add_frame(case,*,nonce,forbidden,enabled=False):
    if (enabled is not True or type(nonce) is not str or not _TOKEN.fullmatch(nonce) or
        type(forbidden) not in (tuple,list,set,frozenset) or any(type(x) is not str for x in forbidden) or
        nonce in forbidden or nonce==archive.REGISTRY_EPOCH):
        raise ValueError('fresh, explicitly enabled frame context required')
    lab=Path(case)/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    script=ui/'authority_frame_read.lua';screen=md/'authority_frame_read.xml'
    if script.exists() or screen.exists():raise ValueError('frame already installed')
    manifest=lab/'ui.xml';config=ui/'config.lua';owner=ui/'authority_download_load_probe.lua'
    manifest_text=manifest.read_text();config_text=config.read_text(encoding='ascii');owner_text=owner.read_text()
    hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    old=" if state=='done' then X4LAN_PARTICIPANT_JOB_TICK();return end\n"
    marker="local state='initial';local failed=false\n"
    if not config_text.endswith('}\n'):raise ValueError('unexpected private config')
    once=motion.base.transfer.once
    manifest_text=once(manifest_text,hook,'    <file name="ui/authority_frame_read.lua" />\n'+hook)
    owner_text=once(owner_text,marker,marker+'local frame_handoff=false\n')
    owner_text=once(owner_text,old," if state=='done' then\n  if not frame_handoff then\n   X4LAN_FRAME_READ_TICK()\n   if X4LAN_FRAME_READ_DONE() then frame_handoff=true else return end\n  end\n  X4LAN_PARTICIPANT_JOB_TICK();return\n end\n")
    literal=motion.base.base.base.lua_literal
    config_text=config_text[:-2]+(',authority_frame_enabled=true,authority_frame_epoch='+literal(archive.REGISTRY_EPOCH)+
        ',authority_frame_nonce='+literal(nonce)+',authority_frame_ship_index='+str(frame.SHIP_INDEX)+
        ',authority_frame_sector='+literal(frame.SECTOR)+'}\n')
    shutil.copyfile(ROOT/'tools/dev/authority_frame_read.lua',script)
    shutil.copyfile(ROOT/'tools/dev/authority_frame_read.xml',screen)
    manifest.write_text(manifest_text);config.write_text(config_text,encoding='ascii');config.chmod(0o600);owner.write_text(owner_text)
    return [script,screen]

def install_server(case,profile,ticket,settings,witnesses,configuration,*,frame_nonce,enabled=False):
    if enabled is not True or type(configuration) is not dict or configuration.get('saved_baseline') is not True or configuration.get('saved_apply') is not True:
        raise ValueError('explicit saved-baseline one-shot diagnostic required')
    forbidden=[v for d in (ticket,settings,configuration) for v in d.values() if type(v) is str]
    if type(frame_nonce) is not str or not _TOKEN.fullmatch(frame_nonce) or frame_nonce in forbidden or frame_nonce==archive.REGISTRY_EPOCH:
        raise ValueError('invalid server frame nonce')
    files=motion.install(case,profile,ticket,settings,witnesses,configuration)
    return files+add_frame(case,nonce=frame_nonce,forbidden=forbidden,enabled=True)
