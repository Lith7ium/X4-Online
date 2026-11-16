"""Independent, bounded log correlation for the private pose observation trial.

The markers are emitted by the diagnostic process; they are not an independent
native call trace or proof of a common reference frame or sustained control.
"""
import math
import re
from authority.experimental_tcp_motion import motion_digest, motion_value

TAG='[X4LAN] AUTH_MOTION_APPLY '
BUFFER='[X4LAN] AUTH_PARTICIPANT_MOTION BUFFERED '
TOKEN=re.compile(r'[0-9a-f]{32}\Z')


def verify_observations(raw, samples, observed_sequences, skipped_near_sequences):
    if type(raw) is not bytes or not raw.endswith(b'\n') or type(samples) is not list or not 2<=len(samples)<=32:
        raise ValueError('incomplete observation evidence')
    samples=[motion_value(s) for s in samples]
    events=[]
    for line in raw.decode('utf-8').splitlines():
        if BUFFER in line:
            events.append(('BUFFERED',line.split(BUFFER,1)[1].strip().split()))
        if TAG in line:
            row=line.split(TAG,1)[1].strip().split()
            if not row:raise ValueError('empty observation marker')
            events.append((row[0],row[1:]))
    if (type(observed_sequences) is not list or type(skipped_near_sequences) is not list or
        len(observed_sequences)<2 or len(observed_sequences)>8 or
        any(type(v) is not int for v in observed_sequences+skipped_near_sequences) or
        sorted(observed_sequences+skipped_near_sequences)!=[s['sequence'] for s in samples] or
        len(set(observed_sequences+skipped_near_sequences))!=len(samples)):
        raise ValueError('invalid observation/skip partition')
    observed=set(observed_sequences);requests=set();out=[];offset=0;last_game=None
    for s in samples:
        written=s['sequence'] in observed
        names=['BUFFERED','PREFLIGHT']+(['INTENT','WRITE_ENTERED','IMMEDIATE'] if written else [])
        chunk=events[offset:offset+len(names)];offset+=len(names)
        if [name for name,_ in chunk]!=names:raise ValueError('observation marker count or order differs')
        b,p=[r for _,r in chunk[:2]]
        ident=[str(s['index']),str(s['sequence']),motion_digest(s)]
        if b!=[ident[0],ident[1],s['sector_macro'],format(s['source_time'],'.17g')]:
            # Both Lua and Python use %.17g; compare numerically to tolerate
            # implementation-specific exponent formatting, without accepting
            # a different timestamp.
            if len(b)!=4 or b[:3]!=[ident[0],ident[1],s['sector_macro']]:raise ValueError('bound sample differs')
            try:t=float(b[3])
            except ValueError:raise ValueError('invalid source time') from None
            if not math.isfinite(t) or t!=s['source_time']:raise ValueError('bound time differs')
        if len(p)!=13 or not TOKEN.fullmatch(p[0]) or p[1:4]!=ident or p[0] in requests:
            raise ValueError('preflight request identity differs')
        requests.add(p[0])
        try:pre=list(map(float,p[4:12]))
        except ValueError:raise ValueError('invalid preflight number') from None
        if not all(math.isfinite(x) for x in pre):raise ValueError('nonfinite preflight')
        target=[s[k] for k in ('x','y','z')]
        if (pre[3:6]!=target or (last_game is not None and pre[6]<last_game) or
            not math.isclose(pre[7],math.dist(pre[:3],target),rel_tol=1e-9,abs_tol=1e-6) or
            (written and (p[12]!='READY' or not 5<=pre[7]<=50)) or
            (not written and (p[12]!='NEAR' or not 0<=pre[7]<5))):
            raise ValueError('preflight values differ')
        last_game=pre[6]
        if not written:
            out.append({'index':s['index'],'sequence':s['sequence'],'sample_sha256':ident[2],
                'source_time':s['source_time'],'target':target,'preflight_position':pre[:3],
                'preflight_game_time':pre[6],'preflight_distance':pre[7],'outcome':'near_skipped'})
            continue
        i,w,a=[r for _,r in chunk[2:]]
        if (len(i)!=11 or len(w)!=1 or len(a)!=8 or not TOKEN.fullmatch(i[0]) or
            i[0]!=w[0] or i[0]!=a[0] or i[1:4]!=ident or a[1:4]!=ident or i[0] in requests):
            raise ValueError('observation request identity differs')
        requests.add(i[0])
        try:intent=list(map(float,i[4:11]));immediate=list(map(float,a[4:8]))
        except ValueError:raise ValueError('invalid observation number') from None
        if (not all(math.isfinite(x) for x in intent+immediate) or intent[3:6]!=target or
            not 5<=math.dist(intent[:3],target)<=50 or intent[6]<pre[6] or immediate[3]<intent[6]):
            raise ValueError('observation values differ')
        last_game=immediate[3]
        out.append({'index':s['index'],'sequence':s['sequence'],'sample_sha256':ident[2],
            'source_time':s['source_time'],'target':target,'preflight_position':pre[:3],
            'preflight_game_time':pre[6],'preflight_distance':pre[7],
            'write_position_before':intent[:3],'write_game_time':intent[6],
            'immediate_position':immediate[:3],'immediate_game_time':immediate[3],
            'immediate_error':math.dist(immediate[:3],target),'outcome':'observed'})
    if offset!=len(events):raise ValueError('extra observation markers')
    return out
