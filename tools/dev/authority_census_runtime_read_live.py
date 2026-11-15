#!/usr/bin/env python3
"""Opt-in paused read of a pinned census archive; import never launches X4."""
import argparse
import json
import math
from pathlib import Path
import re
import secrets
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.checkpoints import _read_regular
import authority_sector_read_live as base
import authority_census_archive_provenance as archive

archive._path_fingerprints=archive.fingerprints
TAG='[X4LAN] AUTH_CENSUS_RUNTIME '
NUMBER=base.NUMBER
ROW=re.compile(r'ROW index=([1-9][0-9]*) status=(ok|unavailable|no_sector|docked_or_stored|local_invalid)(?: local_sector=(0[xX][0-9a-fA-F]{1,16}) x=('+NUMBER+r') y=('+NUMBER+r') z=('+NUMBER+r'))?\Z',re.ASCII)
DONE=re.compile(r'DONE requested=([0-9]+) ok=([0-9]+) unavailable=([0-9]+) no_sector=([0-9]+) docked_or_stored=([0-9]+) local_invalid=([0-9]+) sectors=([0-9]+) game=('+NUMBER+r')\Z',re.ASCII)


def origin_scripts(store,profile):
    origin=store.parent/'server/case'
    if _read_regular(origin/'home/.config/EgoSoft/X4/45841/content.xml',65536)!=_read_regular(profile/'content.xml',65536):
        raise ValueError('archive and private extension lists differ')
    for name in ('authority_checkpoint_marker.xml','authority_ship_registry.xml','authority_identity_fixture.xml'):
        if _read_regular(origin/'extensions/x4_lan_lab/md'/name,1<<20)!=_read_regular(ROOT/'tools/dev'/name,1<<20):
            raise ValueError('archive and read probe saved-state scripts differ: '+name)


def install(case,profile,ticket,slot,nonce,limit,deadline):
    if slot!=1 or not re.fullmatch(r'[0-9a-f]{32}',nonce) or not 1<=limit<=archive.COUNT:
        raise ValueError('invalid census configuration')
    config=base.load.install_probe(case,profile,ticket)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    md_names=('authority_checkpoint_marker.xml','authority_ship_registry.xml','authority_identity_fixture.xml',
              'authority_census_runtime_read.xml')
    ui_names=('authority_checkpoint_marker_probe.lua','authority_registry_resolve_string.lua','authority_census_runtime_read.lua')
    for name in md_names: shutil.copyfile(ROOT/'tools/dev'/name,md/name)
    for name in ui_names: shutil.copyfile(ROOT/'tools/dev'/name,ui/name)
    marker=ui/'authority_checkpoint_marker_probe.lua';text=marker.read_text()
    hook="if phase~='load' or state~='inspect' or type(marker)~='string'"
    if text.count(hook)!=1: raise ValueError('unexpected marker probe')
    marker.write_text(text.replace(hook,"if marker~=cfg.authority_expected_marker or phase~='load' or state~='inspect' or type(marker)~='string'"))
    text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected config')
    text=text[:-2]+(',authority_marker_phase="load",authority_expected_marker="'+archive.MARKER+'",'
        'authority_census_runtime_read=true,authority_census_epoch="'+archive.REGISTRY_EPOCH+'",'
        'authority_census_nonce="'+nonce+'",authority_census_limit='+str(limit)+',authority_census_deadline='+str(deadline)+
        ',authority_census_save_path='+base.base.lua_literal(str(profile/'save'))+'}\n')
    config.write_text(text,encoding='ascii');config.chmod(0o600)
    manifest=lab/'ui.xml';text=manifest.read_text();hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    if text.count(hook)!=1: raise ValueError('missing load manifest hook')
    manifest.write_text(text.replace(hook,''.join('    <file name="ui/'+n+'" />\n' for n in ui_names)+hook))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text()
    hook="local state='initial';local failed=false\n"
    if text.count(hook)!=1: raise ValueError('missing load owner state')
    text=text.replace(hook,hook+'local pause_requested=false;local started_census=false\n')
    hook=" elseif state=='observing' then\n"
    if text.count(hook)!=1: raise ValueError('missing load owner hook')
    text=text.replace(hook,hook+'''  if not engine.is_paused() then
   if started_census then error('census pause lost') end
   if not pause_requested then pause_requested=true;engine.pause() end
   return
  end
  started_census=true
  if not X4LAN_AUTHORITY_MARKER_READY() then return end
  if not X4LAN_CENSUS_RUNTIME_READY() then return end
''')
    owner.write_text(text)
    if {p.name for p in md.iterdir()}!=set(md_names): raise ValueError('unexpected private MD scripts')
    return [config,lab/'ui.xml',lab/'content.xml',profile/'content.xml',profile/'config.xml']+[
        md/name for name in md_names]+[ui/name for name in (*ui_names,'sha256.lua','client_load_barrier.lua',
        'x4_client_load_engine.lua','authority_download_load_probe.lua')]


def validate(raw,ticket,slot,*,partial=False,limit):
    if not raw.endswith(b'\n'):
        if partial: return None
        raise ValueError('incomplete log')
    done_marker=(TAG+'DONE ').encode()
    if partial and done_marker not in raw: return None
    lines=raw.decode('utf-8').splitlines()
    rows=[]
    for line in lines:
        for tag in (base.load.TAG.decode(),'[X4LAN] AUTH_MARKER load ',TAG):
            if tag in line: rows.append((tag,line.split(tag,1)[1].strip()))
    if partial and len(rows)<limit+4: return None
    if len(rows)!=limit+4: raise ValueError('missing or duplicate census/load receipts')
    load_tag=base.load.TAG.decode();marker_tag='[X4LAN] AUTH_MARKER load '
    load_fields='|'.join(str(ticket[k]) for k in base.load.FIELDS)
    if rows[0]!=(load_tag,'load_requested|'+load_fields) or rows[1]!=(marker_tag,'INSPECTED '+archive.MARKER):
        raise ValueError('unexpected load or marker receipt')
    if rows[-1]!=(load_tag,'pause_observed|'+load_fields): raise ValueError('missing pause receipt')
    counts={'ok':0,'unavailable':0,'no_sector':0,'docked_or_stored':0,'local_invalid':0};sectors=set()
    for number,(tag,row) in enumerate(rows[2:-2],1):
        m=ROW.fullmatch(row)
        if tag!=TAG or not m or int(m[1])!=number: raise ValueError('invalid census row order')
        status=m[2];counts[status]+=1
        if status=='ok':
            if m[3] is None or not all(math.isfinite(float(m[j])) for j in (4,5,6)):
                raise ValueError('invalid sector position')
            sectors.add(int(m[3],16))
            if not int(m[3],16): raise ValueError('invalid local sector')
        elif m[3] is not None: raise ValueError('invalid failure row')
    tag,row=rows[-2];m=DONE.fullmatch(row)
    if (tag!=TAG or not m or [int(m[i]) for i in range(1,8)]!=
        [limit,counts['ok'],counts['unavailable'],counts['no_sector'],counts['docked_or_stored'],counts['local_invalid'],len(sectors)]
        or not math.isfinite(float(m[8])) or float(m[8])<0): raise ValueError('invalid census completion')
    return dict(requested=limit,position_reads=counts['ok'],unavailable=counts['unavailable'],
        no_sector=counts['no_sector'],docked_or_stored=counts['docked_or_stored'],local_invalid=counts['local_invalid'],local_sectors=len(sectors),
        reported_game_time=float(m[8]),pause_checked_in_probe=True,runtime_binding_proven=False,
        exact_loaded_file_proven=False,universe_coverage_proven=False)


def ensure_separate(out,store):
    out=Path(out).resolve()
    source=Path(store).resolve(strict=True).parent
    if out.is_relative_to(source) or source.is_relative_to(out):
        raise ValueError('output and source experiment must be separate')


def run(args):
    if not 1<=args.limit<=archive.COUNT or not math.isfinite(args.timeout) or args.timeout<60:
        raise ValueError('invalid limit or timeout')
    ensure_separate(base.snapshot.output_path(args.out),base.base.local_directory(args.store))
    nonce=secrets.token_hex(16)
    old=(base.archive,base.install,base.check_origin_scripts,base.check_log_bytes,base.fault_log,base.MD)
    try:
        # Full log continuity remains checked each poll and again after process
        # shutdown. A large census needs fewer whole-log reads than a 2-row probe.
        args.poll_interval=1.0
        base.archive=archive
        base.MD=('authority_checkpoint_marker.xml','authority_ship_registry.xml','authority_identity_fixture.xml')
        base.install=lambda case,profile,ticket,slot: install(case,profile,ticket,slot,nonce,args.limit,args.timeout)
        base.check_origin_scripts=origin_scripts
        base.check_log_bytes=lambda raw,ticket,slot,partial=False: validate(raw,ticket,slot,partial=partial,limit=args.limit)
        base.fault_log=lambda raw: old[4](raw) or (TAG+'ERROR ').encode() in raw
        result=base.run(args)
    finally:
        base.archive,base.install,base.check_origin_scripts,base.check_log_bytes,base.fault_log,base.MD=old
    result.update(scope='one paused isolated Linux X4 census; local diagnostic only; no client or gameplay',
                  native_velocity_sampled=False,universe_coverage_proven=False)
    (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--limit',type=int,default=archive.COUNT);p.add_argument('--timeout',type=float,default=1800)
    p.add_argument('--seed',type=int,default=276944566);p.set_defaults(slot=1)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1


if __name__=='__main__': sys.exit(main())
