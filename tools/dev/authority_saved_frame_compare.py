"""Strict evidence parsing for one paused, read-only two-X4 frame diagnostic.

Comparing a few local anchors cannot prove universal frame equivalence, object
identity across processes, exact load bytes, or behavior after resume.
"""
import math
import re

SECTOR='cluster_115_sector001_macro'
SHIP_INDEX=1318
STATIONS=frozenset(('AAJ-808','UKN-243','RZT-476','LMC-637','OKE-308','UJU-480','LOO-275','SJE-557','ODV-102','UTM-602','SUM-216'))
STATION_MACRO='station_gen_factory_base_01_macro'
STATION_OWNER='pioneers'
TAG='[X4LAN] AUTH_FRAME_READ '
TOKEN=re.compile(r'[0-9a-f]{32}\Z')
NAME=re.compile(r'[A-Za-z0-9_.-]{1,128}\Z')
CODE=re.compile(r'[A-Za-z0-9_-]{1,32}\Z')


def parse(raw,nonce,*,partial=False):
    if type(raw) is not bytes or type(nonce) is not str or not TOKEN.fullmatch(nonce):raise ValueError('invalid frame evidence')
    if not raw.endswith(b'\n'):
        if partial:return None
        raise ValueError('incomplete frame log')
    rows=[];done=None
    try:lines=raw.decode('utf-8').splitlines()
    except UnicodeError:raise ValueError('invalid frame log encoding') from None
    for line in lines:
        if TAG not in line:continue
        p=line.split(TAG,1)[1].strip().split(' ')
        if len(p)<2 or p[1]!=nonce:raise ValueError('foreign frame nonce')
        if p[0]=='ERROR':raise ValueError('frame read fault')
        if done is not None:raise ValueError('frame row after completion')
        if p[0]=='DONE':
            if len(p)!=4 or not re.fullmatch(r'0|[1-9][0-9]*',p[2]):raise ValueError('invalid frame completion')
            try:game=float(p[3])
            except ValueError:raise ValueError('invalid frame game time') from None
            if not math.isfinite(game) or game<0:raise ValueError('invalid frame game time')
            done=(int(p[2]),game);continue
        if p[0]!='ROW' or len(p)!=11 or p[2] not in ('ship','station'):
            raise ValueError('invalid frame row')
        kind,code,macro,owner,sector=p[2:7]
        if not CODE.fullmatch(code) or not NAME.fullmatch(macro) or not NAME.fullmatch(owner) or sector!=SECTOR:
            raise ValueError('invalid frame identity')
        if kind=='station' and (code not in STATIONS or macro!=STATION_MACRO or owner!=STATION_OWNER):
            raise ValueError('unexpected station identity')
        try:game,x,y,z=map(float,p[7:11])
        except ValueError:raise ValueError('invalid frame value') from None
        if not all(math.isfinite(v) for v in (game,x,y,z)) or game<0 or any(abs(v)>1e9 for v in (x,y,z)):
            raise ValueError('invalid frame value')
        if any(r['code']==code for r in rows):raise ValueError('duplicate frame identity')
        rows.append(dict(kind=kind,code=code,macro=macro,faction=owner,sector=sector,game=game,position=(x,y,z)))
        if len(rows)>len(STATIONS)+1:raise ValueError('too many frame rows')
    if done is None:
        if partial:return None
        raise ValueError('frame completion absent')
    ships=[r for r in rows if r['kind']=='ship'];stations=[r for r in rows if r['kind']=='station']
    if len(ships)!=1 or len(stations)!=done[0] or any(r['game']!=done[1] for r in rows):
        raise ValueError('frame completion differs from sampled rows')
    return {'ship':ships[0],'stations':{r['code']:r for r in stations},'game':done[1]}


def noncollinear(points):
    """Three anchors with arms >= 1000 coordinate units and sine >= 0.05."""
    for i,a in enumerate(points):
        for j,b in enumerate(points):
            if j<=i:continue
            u=tuple(b[k]-a[k] for k in range(3));un=math.hypot(*u)
            if un<1000:continue
            for c in points[j+1:]:
                v=tuple(c[k]-a[k] for k in range(3));vn=math.hypot(*v)
                if vn<1000:continue
                cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                if math.hypot(*cross)>=.05*un*vn:return True
    return False


def compare(server,client,*,tolerance=1.0):
    if type(tolerance) not in (int,float) or not math.isfinite(tolerance) or tolerance<=0 or tolerance>1:
        raise ValueError('invalid diagnostic tolerance')
    a,b=server['ship'],client['ship']
    if any(a[k]!=b[k] for k in ('kind','code','macro','faction','sector')):raise ValueError('ship reference differs')
    common=sorted(set(server['stations']) & set(client['stations']))
    if len(common)<3:raise ValueError('fewer than three common stations')
    deltas={}
    for code in common:
        x,y=server['stations'][code],client['stations'][code]
        if any(x[k]!=y[k] for k in ('kind','code','macro','faction','sector')):raise ValueError('station identity differs')
        deltas[code]=math.dist(x['position'],y['position'])
        if deltas[code]>tolerance:raise ValueError('station positions differ')
    if (not noncollinear([server['stations'][code]['position'] for code in common]) or
        not noncollinear([client['stations'][code]['position'] for code in common])):
        raise ValueError('station geometry is degenerate')
    ship_delta=math.dist(a['position'],b['position'])
    if ship_delta>tolerance:raise ValueError('ship positions differ')
    return {'sector':SECTOR,'ship_registry_index':SHIP_INDEX,'ship_code':a['code'],'station_codes':common,
            'station_count':len(common),'max_station_delta':max(deltas.values()),'ship_delta':ship_delta,
            'position_tolerance':tolerance,'geometry_min_arm':1000,'geometry_min_sine':.05,
            'source_game_time':server['game'],'client_game_time':client['game'],
            'cross_process_identity_proven':False,'universal_frame_identity_proven':False,'continuous_pause_proven':False}
