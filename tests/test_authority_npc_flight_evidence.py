"""Synthetic checks only; these do not exercise the X4 flight experiment."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('flight_evidence', ROOT/'tools/dev/authority_npc_flight_evidence.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def inputs():
    epoch='a'*32;frame='cluster_14_sector001_macro';ident={'epoch':epoch,'index':1,'frame':frame}
    order={**ident,'pilot':'present','order':'MoveWait','game_time':0,'real_time':0.}
    source=[];writes=[];readbacks=[]
    for seq in range(1,5):
        point={'x':seq*10.0,'y':0.0,'z':0.0,'vx':10.0,'vy':0.0,'vz':0.0}
        source.append({**ident,**point,'seq':seq,'real_time':float(seq),'game_time':float(seq),
                       'reference_real_time':seq-.5,'reference_x':seq*10.-5.,'reference_y':0.,'reference_z':0.})
        writes.append({**ident,**point,'actor':'guest-local-actor','seq':seq,'real_time':float(seq),'target_x':seq*10+1.,'target_y':0.,'target_z':0.})
        readbacks.append({**ident,'actor':'guest-local-actor','seq':seq,'real_time':seq+.1,'x':seq*10+1.,'y':0.,'z':0.})
    return dict(epoch=epoch,index=1,frame=frame,guest_actor='guest-local-actor',order=order,source=source,guest_writes=writes,guest_readbacks=readbacks)


class NaturalFlightEvidenceTest(unittest.TestCase):
    def test_correlated_positions_with_advancing_game_clock(self):
        result=module.validate(**inputs())
        self.assertEqual(result['matching_guest_readbacks'],4)
        self.assertFalse(result['npc_flight_proven_by_checker_alone'])

    def test_refuses_weak_or_conflicting_evidence(self):
        for mutation in ('clock','pilot','frame','rate','wrong_reference','future_reference',
                         'source_before_order','readback_before_write','stale_readback','readback_actor','readback_frame'):
            data=copy.deepcopy(inputs())
            if mutation=='clock':
                for row in data['source']: row['game_time']=1.
            elif mutation=='pilot': data['order']['pilot']='unknown'
            elif mutation=='frame': data['source'][2]['frame']='other'
            elif mutation=='rate': data['guest_writes'][1]['vx']=999.
            elif mutation=='wrong_reference': data['source'][1]['reference_x']+=1.
            elif mutation=='future_reference': data['source'][1]['reference_real_time']=data['source'][1]['real_time']+.1
            elif mutation=='source_before_order': data['order']['real_time']=1.
            elif mutation=='readback_before_write':
                for row in data['guest_readbacks']: row['real_time']=0.
            elif mutation=='stale_readback': data['guest_readbacks'][0]['real_time']=1.9
            elif mutation=='readback_actor': data['guest_readbacks'][0]['actor']='other'
            else: data['guest_readbacks'][0]['frame']='other'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                module.validate(**data)
