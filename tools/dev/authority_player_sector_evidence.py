#!/usr/bin/env python3
"""Offline saved-reference/ancestry check for the opt-in two-ship fixture.

Expected MD serialization is inferred from other native fixtures, not yet
observed for this script. This checker does not run X4, verify an empty pilot
seat at runtime, inspect collision geometry, or prove the loaded file.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
from authority.checkpoints import Checkpoint
from authority.marker_evidence import _parse, verify_saved_marker
from authority_registry_save_evidence import COMPONENT, DECIMAL, EPOCH


class PlayerFixtureEvidenceError(ValueError): pass


def verify(checkpoint, epoch, marker):
    if not isinstance(checkpoint, Checkpoint) or not isinstance(epoch,str) or not EPOCH.fullmatch(epoch):
        raise PlayerFixtureEvidenceError('invalid checkpoint or epoch')
    if (not isinstance(marker,str) or not re.fullmatch(r'[0-9a-f]{32}',marker)
            or checkpoint.marker != marker):
        raise PlayerFixtureEvidenceError('invalid marker')
    verify_saved_marker(checkpoint, marker, script_name='X4AuthorityPlayerFixtureMarker', cue_name='MarkerState')
    wanted = {'X4AuthorityPlayerSectorFixture':{'$ready','$pending','$faulted','$epoch','$sector1','$sector2','$ship1','$ship2'},
              'X4AuthoritySectorReferenceFixture':{'$epoch','$sector1','$sector2'}}
    counts = {name:[0,0,0] for name in wanted}; fields={name:{} for name in wanted}
    active = None; cue = False
    def state(path, attrs):
        nonlocal active,cue
        if path == ['savegame','md','script']:
            active = attrs.get('name') if attrs.get('name') in wanted else None; cue=False
            if active: counts[active][0]+=1
        elif path == ['savegame','md','script','cue']:
            cue = bool(active and attrs.get('name')=='State')
            if cue: counts[active][1]+=1
        elif path == ['savegame','md','script','cue','vars'] and cue:
            counts[active][2]+=1
        elif path == ['savegame','md','script','cue','vars','value'] and cue:
            name=attrs.get('name')
            if name in wanted[active]:
                if name in fields[active]: raise PlayerFixtureEvidenceError('duplicate fixture field')
                fields[active][name]=dict(attrs)
    _parse(checkpoint,state)
    if any(counts[n] != [1,1,1] or set(fields[n]) != wanted[n] for n in wanted):
        raise PlayerFixtureEvidenceError('missing or ambiguous fixture state')
    player=fields['X4AuthorityPlayerSectorFixture']; original=fields['X4AuthoritySectorReferenceFixture']
    for key, value in (('$ready','1'),('$pending',None),('$faulted',None)):
        if player[key].get('type')!='integer' or player[key].get('value') != value:
            raise PlayerFixtureEvidenceError('fixture is incomplete or faulted')
    epoch_refs=[]
    for group in (player,original):
        field=group['$epoch']; value=field.get('value','')
        if field.get('type')!='string' or not DECIMAL.fullmatch(value):
            raise PlayerFixtureEvidenceError('invalid epoch reference')
        epoch_refs.append(value)
    def component(group,key):
        field=group[key]; match=COMPONENT.fullmatch(field.get('value',''))
        if field.get('type')!='component' or not match: raise PlayerFixtureEvidenceError('invalid component reference')
        return format(int(match.group(1),16),'x')
    ships=[component(player,'$ship1'),component(player,'$ship2')]
    sectors=[component(player,'$sector1'),component(player,'$sector2')]
    if len(set(ships+sectors)) != 4 or sectors != [component(original,'$sector1'),component(original,'$sector2')]:
        raise PlayerFixtureEvidenceError('fixture slots or saved sector references differ')
    found={}; epochs={}; ancestors=[]; wanted_components=set(ships+sectors); epoch_ids=set(epoch_refs)
    group=None
    def tree(path, attrs):
        nonlocal group
        del ancestors[len(path)-1:]
        ancestors.append((path[-1],dict(attrs) if path[-1]=='component' else {}))
        if path == ['savegame','script','refs']: group=attrs.get('type')
        elif path == ['savegame','script','refs','ref'] and group=='string' and attrs.get('id') in epoch_ids:
            ident=attrs['id']
            if ident in epochs: raise PlayerFixtureEvidenceError('duplicate epoch ref')
            epochs[ident]=attrs.get('string')
        if len(path)<3 or path[:2]!=['savegame','universe'] or path[-1]!='component': return
        match=COMPONENT.fullmatch(attrs.get('id',''))
        if not match: return
        ident=format(int(match.group(1),16),'x')
        if ident not in wanted_components: return
        if ident in found: raise PlayerFixtureEvidenceError('duplicate saved component')
        parents=[a for tag,a in ancestors[:-1] if tag=='component']
        found[ident]=(dict(attrs),parents)
    _parse(checkpoint,tree)
    if set(epochs)!=epoch_ids or any(value!=epoch for value in epochs.values()):
        raise PlayerFixtureEvidenceError('fixture epoch differs')
    if set(found)!=wanted_components: raise PlayerFixtureEvidenceError('fixture component missing')
    for ship,sector in zip(ships,sectors):
        attrs,parents=found[ship]; sector_attrs,_=found[sector]
        if (attrs.get('class')!='ship_s' or attrs.get('macro')!='ship_arg_s_fighter_01_a_macro' or
                attrs.get('owner')!='player' or attrs.get('connection')!='space' or
                sector_attrs.get('class')!='sector' or not parents or parents[-1].get('class')!='zone'):
            raise PlayerFixtureEvidenceError('ship ownership, class, space or parent differs')
        sector_parents=[a for a in parents if a.get('class')=='sector']
        if len(sector_parents)!=1: raise PlayerFixtureEvidenceError('sector parent missing or ambiguous')
        match=COMPONENT.fullmatch(sector_parents[0].get('id',''))
        if not match or format(int(match.group(1),16),'x')!=sector:
            raise PlayerFixtureEvidenceError('ship is not in its saved sector')
    return {'saved_slots_checked':2,'saved_owner_class_sector_checked':True,
            'runtime_seat_proven':False,'positions_proven':False,'collision_free_proven':False,
            'exact_loaded_file_proven':False}
