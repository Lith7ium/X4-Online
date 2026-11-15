"""Validate a local registry-fixture motion log; no gameplay/smoothness claim."""
import math


def _rows(text, marker):
    rows=[]
    for line in text.splitlines():
        if marker not in line:
            continue
        values={}
        for item in line.split(marker,1)[1].split():
            if '=' in item:
                name,value=item.split('=',1)
                if name in values: raise ValueError('duplicate motion field')
                values[name]=value
        rows.append(values)
    return rows


def _float(row,key):
    value=float(row[key])
    if not math.isfinite(value): raise ValueError('nonfinite motion value')
    return value


def validate(server, client, *, epoch, frame):
    source={}
    for row in _rows(server,'REGISTRY_MOTION_SOURCE '):
        if row.get('epoch')!=epoch or row.get('index')!='1' or row.get('frame')!=frame:
            raise ValueError('source registry/frame mismatch')
        seq=int(row['seq'])
        if seq in source: raise ValueError('duplicate source sequence')
        source[seq]=row
    writes=_rows(client,'AUTHORITY_CONTINUOUS_WRITE ')
    observations=_rows(client,'AUTHORITY_CONTINUOUS_OBSERVE ')
    readbacks={}
    for row in observations:
        seq=int(float(row['seq']))
        if seq in readbacks: raise ValueError('duplicate client readback')
        readbacks[seq]=row
    if len(writes)<5: raise ValueError('insufficient client writes')
    last=0;matched=[]
    for row in writes:
        seq=int(float(row['seq']))
        if seq<=last or seq not in source: raise ValueError('unmatched or stale source sequence')
        last=seq;s=source[seq]
        if s.get('rate')!='known': raise ValueError('write has unknown velocity')
        for axis in 'xyz':
            if _float(row,axis)!=_float(s,axis) or _float(row,'v'+axis)!=_float(s,'v'+axis):
                raise ValueError('write differs from source')
            predicted=_float(row,axis)+.1*_float(row,'v'+axis)
            if abs(_float(row,'target_'+axis)-predicted)>1e-6: raise ValueError('invalid prediction')
        if seq in readbacks:
            r=readbacks[seq]
            error=math.dist(tuple(_float(row,'target_'+a) for a in 'xyz'),tuple(_float(r,a) for a in 'xyz'))
            if error<=5: matched.append(tuple(_float(r,a) for a in 'xyz'))
    if len(matched)<5 or max(math.dist(matched[0],point) for point in matched[1:])<10:
        raise ValueError('insufficient matching movement readbacks')
    nudges=_rows(server,'REGISTRY_MOTION_NUDGE ')
    if len(nudges)<3: raise ValueError('source setter impulses missing')
    return {'pass':True,'source_samples':len(source),'guest_writes':len(writes),
            'matching_guest_readbacks':len(matched),'source_controlled_setter_impulses':len(nudges),
            'rate':'source position finite difference in m/s, not native velocity',
            'scope':'one newly created registry fixture, local UDP, paused isolated X4 instances',
            'collision_clearance_proven':False,'atomicity_proven':False,'npc_flight_proven':False,
            'smoothness_proven':False,'gameplay_proven':False}
