"""Two source-game-time samples; no claim of a shared/native frame."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from authority.experimental_motion_pair_evidence import validate_pair

class MotionPairEvidence(unittest.TestCase):
 def setUp(self):
  self.e='a'*32;self.g='b'*32
  self.a={'version':1,'epoch':self.e,'generation':self.g,'index':42,'sequence':1,
          'sector_macro':'sector_a','source_time':10,'x':1,'y':2,'z':3,'velocity':None}
  self.b={**self.a,'sequence':2,'source_time':10.5,'x':2,'velocity':{'x':2,'y':0,'z':0}}
 def check(self,values):return validate_pair(values,epoch=self.e,generation=self.g,index=42,sector='sector_a')
 def test_nonzero_zero_and_unknown_velocity(self):
  self.assertEqual(self.check([self.a,self.b])[1]['velocity']['x'],2)
  zero={**self.b,'x':1,'velocity':{'x':0,'y':0,'z':0}}
  self.assertEqual(self.check([self.a,zero])[1]['velocity'],{'x':0,'y':0,'z':0})
  self.assertIsNone(self.check([self.a,{**self.b,'source_time':12,'velocity':None}])[1]['velocity'])
 def test_mismatch_and_wrong_rate_refused(self):
  for bad in ({**self.b,'index':43},{**self.b,'sequence':3},{**self.b,'sector_macro':'sector_b'},
              {**self.b,'source_time':10},{**self.b,'source_time':9},
              {**self.b,'velocity':{'x':3,'y':0,'z':0}},
              {**self.b,'source_time':12},
              {**self.b,'generation':'c'*32}):
   with self.subTest(bad=bad),self.assertRaises(ValueError):self.check([self.a,bad])
  with self.assertRaises(ValueError):self.check([{**self.a,'velocity':{'x':0,'y':0,'z':0}},self.b])
  with self.assertRaises(ValueError):self.check([self.a])
if __name__=='__main__':unittest.main()
