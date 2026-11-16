"""No X4 or X11 connections: fake process plus real pidfd/exec gate."""
from pathlib import Path
from unittest.mock import patch
import os
import sys
import time
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_x11_key_pulse as m
import authority_x11_private_scope as scope

class Pulse(unittest.TestCase):
 def run_fake(self,mode,guard=lambda:True):
  p=m.OneKeyPulse(enabled=True);s={'owner_pid':os.getpid()}
  with patch.object(m,'WORKER',ROOT/'tests/authority_x11_pulse_fake_worker.py'),patch.object(scope,'verify',lambda *a,**k:True),patch.dict(os.environ,{'FAKE_PULSE_MODE':mode}):
   if mode=='ok':
    result=p.run(s,duration=.1,deadline=time.monotonic()+4,guard=guard)
    self.assertTrue(result['server_key_up_observed']);self.assertFalse(result['x4_input_received_proven'])
    self.assertTrue(p.cleanup_before_owned_processes());self.assertTrue(all(h.pidfd is None for h in p.helpers))
    with self.assertRaises(RuntimeError):p.run(s,duration=.1,deadline=time.monotonic()+4,guard=guard)
   elif mode=='release_fail':
    with self.assertRaises(m.KeyReleaseUnconfirmed):p.run(s,duration=.1,deadline=time.monotonic()+4,guard=guard)
    with self.assertRaises(m.KeyReleaseUnconfirmed):p.cleanup_before_owned_processes()
   else:
    with self.assertRaises((RuntimeError,TimeoutError)):p.run(s,duration=.1,deadline=time.monotonic()+4,guard=guard)
    self.assertTrue(p.up_confirmed);self.assertTrue(p.cleanup_before_owned_processes())
    self.assertGreaterEqual(len(p.helpers),2)
 def test_success(self):self.run_fake('ok')
 def test_worker_crash_after_go_releases_independently(self):self.run_fake('crash_after_go')
 def test_worker_crash_after_down_releases_independently(self):self.run_fake('crash_after_down')
 def test_unconfirmed_release_retains_lock(self):self.run_fake('release_fail')
 def test_disabled_and_invalid_scope_do_not_spawn(self):
  with self.assertRaises(ValueError):m.OneKeyPulse()
  p=m.OneKeyPulse(enabled=True)
  with self.assertRaises(ValueError):p.run({'owner_pid':os.getpid()+1},duration=.1,deadline=time.monotonic()+1,guard=lambda:True)
  self.assertEqual(p.helpers,[])
  with self.assertRaises(ValueError):scope.verify({'display':':0'})
 def test_no_send_on_guard_failure(self):
  p=m.OneKeyPulse(enabled=True)
  with patch.object(scope,'verify',lambda *a,**k:True):
   with self.assertRaises(RuntimeError):p.run({'owner_pid':os.getpid()},duration=.1,deadline=time.monotonic()+1,guard=lambda:False)
  self.assertEqual(p.helpers,[]);self.assertFalse(p.possible_down)

if __name__=='__main__':unittest.main()
