"""Offline lifecycle, motion result, and correlated log checks; no X4 start."""
import argparse
import json
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_source_motion_pair_live as m

class MotionPair(unittest.TestCase):
 def setUp(self):
  with patch.object(m.MotionCoordinator,'_sources',side_effect=m.pair.Coordinator._sources):
   self.c=m.MotionCoordinator({'sector_a':(1,2)},defer_source_ack=True)
  self.c.add_role('server');self.c.add_role('client');self.addCleanup(self.c.cleanup_after_owned_processes)
 def result(self):
  sample={'version':1,'epoch':m.archive.REGISTRY_EPOCH,'generation':self.c.generation,'index':m.archive.COUNT+1,
    'sequence':1,'sector_macro':'sector_a','source_time':102.125,'x':1,'y':2,'z':3,'velocity':None}
  return {'event':'result','ok':True,'tcp_admitted':True,'tcp_job_receipt':True,'source_md_ack_observed':True,
   'client_md_ffi_asserted_by_owner':True,'synthetic_server_checkpoint_and_admission':True,
   'source_activation_is_birth':False,'descriptor_atomic':False,'frame_identity_proven':False,
   'event_sequence':1,'index':m.archive.COUNT+1,'sector_macro':'sector_a','macro':'ship_a','faction':'argon',
   'motion_sample':sample,'motion_client_bound_buffered':True,
   'motion_velocity_source':'position_difference_per_source_game_second','motion_frame_identity_proven':False}
 def test_correlated_sample_and_buffer_log_required(self):
  result=self.result();self.c._validate_motion_result(result);self.c.result=result;self.c.tickets['client']={}
  source=b'[X4LAN] AUTH_SOURCE_SINGLE STATE binding 10\n[X4LAN] AUTH_SOURCE_SINGLE STATE observing 10\n[X4LAN] AUTH_SOURCE_SINGLE STATE done 11\n'
  client=b'[X4LAN] AUTH_PARTICIPANT_MOTION BUFFERED 10055 1 sector_a 102.125\n'
  with patch.object(self.c,'check_sources',return_value=True),patch.object(m.pair.client_evidence,'observe',return_value={'local_job_applied':True}):
   self.assertTrue(self.c.verify_final({'server':source,'client':client}))
   for bad in (b'\n',client.replace(b'10055',b'10056'),client.replace(b'102.125',b'102.126'),client+client):
    with self.assertRaises(ValueError):self.c.verify_final({'server':source,'client':bad})
  for change in ({'motion_client_bound_buffered':False},{'motion_frame_identity_proven':True},
                 {'motion_sample':{**result['motion_sample'],'index':10056}},{'extra':True}):
   with self.assertRaises(ValueError):self.c._validate_motion_result({**result,**change})
 def test_installs_distinct_endpoints_and_saved_witnesses(self):
  ticket={'world_epoch':self.c.attempt}
  with patch.object(self.c,'check_sources',return_value=True),patch.object(m.source_install,'install',return_value=[]) as source,patch.object(m.client_install,'install',return_value=[]) as client:
   self.c.install(Path('/case-a'),Path('/profile-a'),ticket,{'role':'server'},'x',120,60)
   self.c.install(Path('/case-b'),Path('/profile-b'),ticket,{'role':'client'},'y',120,60)
  a=source.call_args.args[3];b=client.call_args.args[3];motion=client.call_args.args[5]
  self.assertEqual(a['epoch'],motion['epoch']);self.assertEqual(a['generation'],motion['generation'])
  self.assertEqual(client.call_args.args[4],{'sector_a':(1,2)})
  self.assertEqual(len({a['control_port'],a['job_port'],a['motion']['port'],b['participant_port'],b['job_port'],motion['port']}),6)
 def test_source_fingerprints_cover_motion_overlay_inputs(self):
  sources=set(m.MotionCoordinator._sources())
  for path in ('src/authority/lua/motion_buffer.lua','src/authority/lua/motion_client_owner.lua',
               'src/authority/lua/source_motion_sampler.lua','tools/dev/authority_replica_motion_bind.xml',
               'tools/dev/authority_multi_create_receiver.xml','tools/dev/authority_participant_job_session.lua',
               'tools/dev/authority_motion_ipc_supervisor.py'):
   self.assertIn(ROOT/path,sources)
 def test_chunked_result_with_expensive_guard_and_strict_suffix_fence(self):
  receive,send=socket.socketpair();self.addCleanup(receive.close);self.addCleanup(send.close)
  result=self.result();result['motion_sample']['sector_macro']='sector_'+('a'*100)
  wire=json.dumps(result,separators=(',',':')).encode()+b'\n'
  self.assertGreater(len(wire),700);send.sendall(wire);send.shutdown(socket.SHUT_WR)
  calls=[]
  def costly_guard():calls.append(1);time.sleep(.002);return True
  reader=m.pair.ProgressFrames(receive);deadline=time.monotonic()+2
  self.assertEqual(json.loads(reader.read(deadline,costly_guard)),result)
  m.finish_worker_output(receive,reader,deadline,costly_guard)
  self.assertLess(len(calls),12)
 def test_buffered_or_socket_suffix_cannot_be_accepted_as_one_result(self):
  for suffix_in_buffer in (True,False):
   receive,send=socket.socketpair()
   try:
    reader=m.pair.ProgressFrames(receive)
    if suffix_in_buffer:reader.buffer.extend(b'foreign\n')
    else:send.sendall(b'foreign\n')
    send.shutdown(socket.SHUT_WR)
    with self.assertRaises(RuntimeError):m.finish_worker_output(receive,reader,time.monotonic()+2,lambda:True)
   finally:receive.close();send.close()
 def test_buffered_result_still_requires_guard_and_deadline(self):
  receive,send=socket.socketpair();self.addCleanup(receive.close);self.addCleanup(send.close)
  reader=m.pair.ProgressFrames(receive);reader.buffer.extend(b'{"ok":true}\n')
  def failed_guard():raise RuntimeError('context lost')
  with self.assertRaisesRegex(RuntimeError,'context lost'):reader.read(time.monotonic()+2,failed_guard)
  with self.assertRaises(TimeoutError):reader.read(time.monotonic()-1,lambda:True)
 def test_lifecycle_hooks_restored_on_refusal(self):
  with tempfile.TemporaryDirectory() as out:
   args=argparse.Namespace(window=1,out=Path(out))
   original=(m.lifecycle.coordinator.CensusCoordinator,m.lifecycle.installer.install,m.lifecycle.owned.spawn_owned_gated,m.lifecycle.load_observation)
   with patch.object(m.lifecycle,'run',return_value={'success':False}):self.assertFalse(m.run(args)['success'])
   self.assertEqual(original,(m.lifecycle.coordinator.CensusCoordinator,m.lifecycle.installer.install,m.lifecycle.owned.spawn_owned_gated,m.lifecycle.load_observation))
if __name__=='__main__':unittest.main()
