"""Offline strict frame evidence and geometry tests; no X4 launch."""
import unittest
from tools.dev import authority_saved_frame_compare as m
N='a'*32

def log(stations=None,ship=(12,20,30),nonce=N):
 if stations is None:stations=[('AAJ-808',(0,0,0)),('UKN-243',(2000,0,0)),('RZT-476',(0,2000,0))]
 rows=[f'{m.TAG}ROW {nonce} ship ABC-123 ship_macro argon {m.SECTOR} 10 {ship[0]} {ship[1]} {ship[2]}']
 rows += [f'{m.TAG}ROW {nonce} station {code} {m.STATION_MACRO} {m.STATION_OWNER} {m.SECTOR} 10 {p[0]} {p[1]} {p[2]}' for code,p in stations]
 rows.append(f'{m.TAG}DONE {nonce} {len(stations)} 10')
 return ('\n'.join(rows)+'\n').encode()

class FrameEvidence(unittest.TestCase):
 def test_matching_frames_and_ship(self):
  data=m.parse(log(),N);result=m.compare(data,m.parse(log(),N))
  self.assertEqual(result['station_count'],3);self.assertFalse(result['universal_frame_identity_proven'])
 def test_mismatch_and_degenerate_fence(self):
  a=m.parse(log(),N)
  cases=[log(ship=(14,20,30)),log([('AAJ-808',(0,0,0)),('UKN-243',(2000,0,0)),('RZT-476',(0,2002,0))]),
         log([('AAJ-808',(0,0,0)),('UKN-243',(2000,0,0))]),
         log([('AAJ-808',(0,0,0)),('UKN-243',(2000,0,0)),('RZT-476',(4000,0,0))])]
  for raw in cases:
   with self.subTest(raw=raw):
    with self.assertRaises(ValueError):m.compare(a,m.parse(raw,N))
 def test_foreign_duplicate_or_wrong_metadata_fence(self):
  cases=[log(nonce='b'*32),log().replace(b'pioneers',b'argon',1),log().replace(b'UKN-243',b'AAJ-808',1),
         log().replace(b'DONE '+N.encode()+b' 3',b'DONE '+N.encode()+b' 4'),log()+log()]
  for raw in cases:
   with self.subTest(raw=raw[:30]):
    with self.assertRaises(ValueError):m.parse(raw,N)
 def test_pause_clock_changes_and_partial(self):
  self.assertIsNone(m.parse(log().split(b'DONE')[0],N,partial=True))
  with self.assertRaises(ValueError):m.parse(log().replace(b' sector001',b' other',1).replace(b' DONE ',b' DONE '), 'f'*32)
  with self.assertRaises(ValueError):m.parse(log().replace(b' 10 0 2000 0',b' 11 0 2000 0'),N)

if __name__=='__main__':unittest.main()
