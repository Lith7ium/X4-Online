"""Synthetic Linux ownership and worker failure checks; no X11 or X4."""
from pathlib import Path
from unittest.mock import patch
import hashlib,os,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_x11_private_scope as m

class Scope(unittest.TestCase):
 def sample(self,root):
  return dict(display=':173',auth=str(root/'auth'),auth_sha256='0'*64,private_root=str(root),owner_pid=10,owner_start=100,
   display_leader=20,display_leader_start=200,server_pid=21,server_start=201,server_exe='/usr/bin/Xwayland',
   x4_leader=30,x4_leader_start=300,x4_pid=31,x4_start=301,x4_exe='/game/X4',window=42)
 def test_process_ownership_and_private_display(self):
  with tempfile.TemporaryDirectory() as d:
   s=self.sample(Path(d));rows={10:{'ppid':1,'group':1,'start':100},20:{'ppid':10,'group':20,'start':200},21:{'ppid':20,'group':20,'start':201},30:{'ppid':10,'group':30,'start':300},31:{'ppid':30,'group':30,'start':301}}
   with patch.object(m,'_process',side_effect=lambda pid,start:rows[pid]),patch.object(m,'_auth'),patch.object(m,'_listeners'),patch.object(os.path,'samefile',return_value=True),patch.object(Path,'read_bytes',return_value=b'DISPLAY=:173\0'):
    self.assertTrue(m.verify(s));self.assertTrue(m.verify(s,require_x4=False))
    for changed in ({'display':':0'},{'owner_pid':99},{'server_exe':'/tmp/bash'},{'window':0}):
     with self.subTest(changed=changed),self.assertRaises((ValueError,KeyError)):m.verify({**s,**changed})
    rows[21]['group']=99
    with self.assertRaises(ValueError):m.verify(s)
    rows[21]['group']=20;rows[31]['group']=99
    with self.assertRaises(ValueError):m.verify(s)
 def test_authority_private_regular_and_pinned(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'auth';p.write_bytes(b'test');p.chmod(0o600)
   s=self.sample(root);s['auth_sha256']=hashlib.sha256(b'test').hexdigest()
   m._auth(s);p.write_bytes(b'changed')
   with self.assertRaises(ValueError):m._auth(s)
   p.unlink();p.symlink_to('/etc/passwd')
   with self.assertRaises(ValueError):m._auth(s)
 def test_all_matching_server_listeners_owned(self):
  rows='header\n0: 00000002 0 00010000 0001 01 123 /tmp/.X11-unix/X173\n0: 00000002 0 00010000 0001 01 124 @/tmp/.X11-unix/X173\n'
  with patch.object(Path,'read_text',return_value=rows),patch.object(Path,'iterdir',return_value=[Path('/proc/21/fd/1'),Path('/proc/21/fd/2')]),patch.object(os,'readlink',side_effect=['socket:[123]','socket:[124]']):m._listeners(':173',21)
  with patch.object(Path,'read_text',return_value=rows),patch.object(Path,'iterdir',return_value=[Path('/proc/21/fd/1')]),patch.object(os,'readlink',return_value='socket:[123]'):
   with self.assertRaises(ValueError):m._listeners(':173',21)
 def test_keyup_on_normal_signal_and_exception(self):
  for mode in ('ok','exception_after_down','signal_after_down','signal_before_down','signal_during_keycheck','deadline_before_down'):
   with self.subTest(mode=mode):
    r=subprocess.run([sys.executable,'tests/authority_x11_pulse_worker_synthetic.py',mode],cwd=ROOT,capture_output=True,text=True,timeout=6)
    self.assertEqual(r.returncode,0,r.stderr)
if __name__=='__main__':unittest.main()
