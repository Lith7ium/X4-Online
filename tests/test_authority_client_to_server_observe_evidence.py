import copy
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.experimental_tcp_motion import motion_digest
from authority_client_to_server_observe_evidence import verify_observations

class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.samples=[{'version':1,'epoch':'a'*32,'generation':'b'*32,'index':1318,'sequence':n,
            'sector_macro':'cluster_115_sector001_macro','source_time':float(n),'x':10.,'y':0.,'z':0.,'velocity':None}
            for n in (1,2,3)]
        self.lines=[]
        for n,s in enumerate(self.samples,1):
            d=motion_digest(s);p=format(2*n,'032x');w=format(2*n+1,'032x')
            self.lines.append(f'[X4LAN] AUTH_PARTICIPANT_MOTION BUFFERED 1318 {n} {s["sector_macro"]} {n}')
            if n==2:
                self.lines.append(f'[X4LAN] AUTH_MOTION_APPLY PREFLIGHT {p} 1318 {n} {d} 9 0 0 10 0 0 4 1 NEAR')
            else:
                self.lines.extend([f'[X4LAN] AUTH_MOTION_APPLY PREFLIGHT {p} 1318 {n} {d} 0 0 0 10 0 0 4 10 READY',
                    f'[X4LAN] AUTH_MOTION_APPLY INTENT {w} 1318 {n} {d} 0 0 0 10 0 0 4',
                    f'[X4LAN] AUTH_MOTION_APPLY WRITE_ENTERED {w}',
                    f'[X4LAN] AUTH_MOTION_APPLY IMMEDIATE {w} 1318 {n} {d} 10 0 0 4'])
    def check(self,lines=None,observed=None,skipped=None):
        return verify_observations(('\n'.join(self.lines if lines is None else lines)+'\n').encode(),self.samples,
            [1,3] if observed is None else observed,[2] if skipped is None else skipped)
    def test_correlated_and_skipped(self):
        result=self.check();self.assertEqual([r['outcome'] for r in result],['observed','near_skipped','observed'])
        self.assertEqual(result[0]['immediate_error'],0)
    def test_reject_wrong_order_and_extra_write(self):
        lines=copy.copy(self.lines);lines[2],lines[3]=lines[3],lines[2]
        with self.assertRaises(ValueError):self.check(lines)
        lines=self.lines+[self.lines[3]]
        with self.assertRaises(ValueError):self.check(lines)
    def test_reject_lost_or_fabricated_skip(self):
        with self.assertRaises(ValueError):self.check(observed=[1,2,3],skipped=[])
        with self.assertRaises(ValueError):self.check(observed=[1,3],skipped=[])
    def test_reject_bad_distance_and_sample_digest(self):
        lines=copy.copy(self.lines);lines[1]=lines[1].replace(' 4 10 READY',' 4 1 READY')
        with self.assertRaises(ValueError):self.check(lines)
    def test_reject_backwards_server_game_clock(self):
        lines=copy.copy(self.lines);lines[2]=lines[2][:-1]+'3'
        with self.assertRaises(ValueError):self.check(lines)
        lines=copy.copy(self.lines);lines[6]=lines[6].replace(' 4 1 NEAR',' 3 1 NEAR')
        with self.assertRaises(ValueError):self.check(lines)
        lines=copy.copy(self.lines);lines[2]=lines[2].replace(motion_digest(self.samples[0]),'0'*64)
        with self.assertRaises(ValueError):self.check(lines)
if __name__=='__main__':unittest.main()
