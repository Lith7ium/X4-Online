#!/usr/bin/env python3
"""Opt-in disposable local flight observation; no input, save or multiplayer."""
import argparse
import json
import math
from pathlib import Path
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_player_control_live as control
import authority_sector_read_live as base
import authority_job_attach_live as readonly

TAG = '[X4LAN] AUTH_PLAYER_FLIGHT_LIVE '
MD = 'authority_player_flight_observer.xml'
UI = ('authority_player_flight_observer.lua', 'authority_player_flight_live_owner.lua')


def replace_once(path, old, new):
    text = path.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise ValueError('unexpected private owner hook')
    path.write_text(text.replace(old, new), encoding='utf-8')


def install(case, profile, ticket, slot, timeout):
    protected = control.install(case, profile, ticket, slot, timeout)
    lab = case/'extensions/x4_lan_lab'; ui = lab/'ui'; md = lab/'md'
    extras = [md/MD, *(ui/name for name in UI)]
    for path in extras:
        shutil.copyfile(ROOT/'tools/dev'/path.name, path)
    config = ui/'config.lua'; text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected configuration')
    config.write_text(text[:-2] + ',authority_player_flight_live=true,authority_player_flight_nonce="' +
                      secrets.token_hex(16) + '",authority_player_flight_timeout=' + format(timeout, '.17g') + '}\n', encoding='ascii')
    owner = ui/'authority_player_control_live_owner.lua'
    replace_once(owner, " local busy,failed=false,false;local phase='new';local mode='pre';local target,locked,probe,outcome\n",
                 " local busy,failed=false,false;local phase='new';local mode='pre';local target,locked,probe,outcome;local handed=false\n")
    replace_once(owner, ' function api:state()return phase end\n', ''' function api:outcome()
  local result;assert(action(function()assert(phase=='done');result=outcome end));return result
 end
 function api:handoff()
  local result;assert(action(function()
   assert(phase=='done' and outcome=='controlled' and locked and target and not handed)
   handed=true;result=target
  end));return result
 end
 function api:state()return phase end
''')
    replace_once(owner, "function X4LAN_PLAYER_CONTROL_LIVE_TICK()if not app:tick()then error('player control probe failed')end end\n",
                 "function X4LAN_PLAYER_CONTROL_LIVE_TICK()if not app:tick()then error('player control probe failed')end end\n"
                 "function X4LAN_PLAYER_CONTROL_LIVE_STATE()return app:state()end\n"
                 "function X4LAN_PLAYER_CONTROL_LIVE_OUTCOME()return app:outcome()end\n"
                 "function X4LAN_PLAYER_CONTROL_LIVE_HANDOFF()return app:handoff()end\n")
    manifest=lab/'ui.xml'
    hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    replace_once(manifest,hook,''.join('    <file name="ui/'+name+'" />\n' for name in UI)+hook)
    update=ui/'authority_download_load_probe.lua'
    replace_once(update," if state=='done' then X4LAN_PLAYER_CONTROL_LIVE_TICK();return end\n",
                 " if state=='done' then X4LAN_PLAYER_FLIGHT_LIVE_TICK();return end\n")
    return protected + extras


def fault(raw):
    return control.fault(raw) or (TAG+'ERROR').lower().encode() in raw.lower()


def validate(raw,ticket,slot,*,partial=False):
    if fault(raw): raise ValueError('flight diagnostic reported a fault')
    observed=control.validate(raw,ticket,slot,partial=partial)
    if not raw.endswith(b'\n') and partial: return None
    lines=raw.decode('utf-8').splitlines()
    controls=[i for i,line in enumerate(lines) if control.TAG+'DONE' in line]
    rows=[(i,line.split(TAG,1)[1].strip()) for i,line in enumerate(lines) if TAG in line]
    if rows and (len(controls)!=1 or rows[0][0]<=controls[0]): raise ValueError('flight before completed control')
    if observed is None: return None
    if observed['outcome']=='inconclusive':
        expected=('INCONCLUSIVE','DONE')
        values=tuple(s for _,s in rows)
        if values!=expected:
            if partial and values==expected[:len(values)]: return None
            raise ValueError('invalid inconclusive flight sequence')
        observed.update(flight_observation_completed=False,flight_observation_outcome='inconclusive')
        return observed
    expected=('ARMED','RESUME_INTENT','RESUME_RETURNED','RUNNING','SAMPLE','SAMPLE','SAMPLE','DONE','FENCED')
    kinds=[];samples=[];armed=None;running=None
    for _,value in rows:
        if value.startswith('ARMED ') or value.startswith('RUNNING '):
            fields=value.split()
            if len(fields)!=3: raise ValueError('invalid transition observation')
            try: point=tuple(float(x) for x in fields[1:])
            except ValueError: raise ValueError('invalid transition time') from None
            if not all(math.isfinite(x) and x>=0 for x in point): raise ValueError('invalid transition time')
            if fields[0]=='ARMED':
                if armed is not None: raise ValueError('duplicate arm')
                armed=point
            else:
                if running is not None or armed is None or point[0]<armed[0] or point[1]<=armed[1]: raise ValueError('game time did not progress')
                running=point
            kinds.append(fields[0])
        elif value.startswith('SAMPLE '):
            fields=value.split()
            if len(fields)!=12: raise ValueError('invalid sample field count')
            try:
                number=int(fields[1]); nums=[float(x) for x in fields[2:]]
            except ValueError: raise ValueError('invalid sample number') from None
            if number!=len(samples)+1 or not all(math.isfinite(x) for x in nums): raise ValueError('invalid sample')
            rb,ra,gb,ga=nums[:4]
            if running is None or rb<running[0] or gb<running[1] or ra<rb or ga<gb or (samples and (rb<=samples[-1][0][1] or gb<=samples[-1][0][3])):
                raise ValueError('sample time order')
            samples.append((nums,number));kinds.append('SAMPLE')
        else: kinds.append(value)
    if tuple(kinds)!=expected:
        if partial and tuple(kinds)==expected[:len(kinds)]: return None
        raise ValueError('invalid flight sequence')
    observed.update(flight_observation_completed=True,flight_observation_outcome='observed',
                    paused_real=armed[0],paused_game=armed[1],running_real=running[0],running_game=running[1],
                    samples=[dict(sequence=n,real_before=a[0],real_after=a[1],game_before=a[2],game_after=a[3],
                                  x=a[4],y=a[5],z=a[6],yaw=a[7],pitch=a[8],roll=a[9]) for a,n in samples],
                    input_proven=False,movement_cause_proven=False,flight_proven=False,multiplayer_proven=False)
    return observed


def run(args):
    if args.slot!=2 or not math.isfinite(args.timeout) or args.timeout<60: raise ValueError('slot 2 and timeout >= 60 required')
    out=base.snapshot.output_path(args.out);store=base.base.local_directory(args.store);source=store.parent
    if out.resolve().is_relative_to(source) or source.is_relative_to(out.resolve()): raise ValueError('output overlaps source')
    before=base.archive._path_fingerprints(store)
    old=(base.install,base.check_log_bytes,base.fault_log,base.base.readonly_save_command,base.result_finalizer)
    def install_private(case,profile,ticket,slot):
        current=base.install
        try:
            base.install=old[0]
            return install(case,profile,ticket,slot,min(args.timeout,120))
        finally: base.install=current
    def finalize(result):
        try:
            if base.archive._path_fingerprints(store)!=before: raise ValueError('checkpoint source changed')
        except BaseException:
            for key in ('outcome','diagnostic_completed','flight_observation_completed','flight_observation_outcome','samples','paused_real','paused_game','running_real','running_game'): result.pop(key,None)
            result['local_control_proven']=False;raise
        if result.get('success') is not True:
            for key in ('outcome','diagnostic_completed','flight_observation_completed','flight_observation_outcome','samples','paused_real','paused_game','running_real','running_game'): result.pop(key,None)
        result.update(scope='one isolated Linux X4; passive player pose observation',checkpoint_requested=False,
                      local_control_proven=result.get('success') is True and result.get('outcome')=='controlled',
                      flight_proven=False,input_proven=False,movement_cause_proven=False,seat_free_proven=False,
                      save_authorized=False,multiplayer_proven=False)
    try:
        base.install=install_private;base.check_log_bytes=validate;base.fault_log=fault
        base.base.readonly_save_command=readonly.readonly_save_command;base.result_finalizer=finalize
        return base.run(args)
    finally:
        (base.install,base.check_log_bytes,base.fault_log,base.base.readonly_save_command,base.result_finalizer)=old


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--store',type=Path,default=base.archive.DEFAULT_STORE);parser.add_argument('--display',required=True)
    parser.add_argument('--timeout',type=float,default=600);parser.add_argument('--seed',type=int,default=276944566)
    args=parser.parse_args();args.slot=2
    try: result=run(args)
    except (OSError,ValueError,RuntimeError) as error: parser.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__': sys.exit(main())
