"""Offline orchestration and final-evidence checks; no X4 execution."""
import argparse
import json
import socket
import time
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_source_tcp_pair_live as m

class Pair(unittest.TestCase):
 def setUp(self):
  self.coord=m.Coordinator({'sector_a':(1,)},defer_source_ack=True)
  self.coord.add_role('server');self.coord.add_role('client')
  self.addCleanup(self.coord.cleanup_after_owned_processes)
 def result(self):
  return {'event':'result','ok':True,'tcp_admitted':True,'tcp_job_receipt':True,'source_md_ack_observed':True,
   'client_md_ffi_asserted_by_owner':True,'synthetic_server_checkpoint_and_admission':True,
   'source_activation_is_birth':False,'descriptor_atomic':False,'frame_identity_proven':False,
   'event_sequence':1,'index':m.archive.COUNT+1,'sector_macro':'sector_a','macro':'ship_a','faction':'argon'}
 def test_changed_worker_fingerprint_fails_closed(self):
  path=next(iter(self.coord.source_fingerprints))
  self.coord.source_fingerprints[path]=('not','the digest')
  with self.assertRaises(ValueError):self.coord.check_sources()
 def test_operator_nesting_error_fences_result(self):
  self.assertTrue(m.private_fault(b'Error: Maximum operator nesting level reached'))
  self.assertFalse(m.private_fault(b'[X4LAN] AUTH_SOURCE_SINGLE STATE binding 1\n'))
 def test_worker_evidence_requires_md_ack_and_saved_sector_witness(self):
  self.coord._validate_result(self.result())
  for change in ({'source_md_ack_observed':False},{'sector_macro':'missing'},{'source_activation_is_birth':True},
                 {'index':m.archive.COUNT+2},{'extra':1}):
   with self.assertRaises(ValueError):self.coord._validate_result({**self.result(),**change})
 def test_source_and_client_final_logs_order(self):
  self.coord.result=self.result();self.coord.tickets['client']={}
  source=b'[X4LAN] AUTH_SOURCE_SINGLE STATE binding 10\n[X4LAN] AUTH_SOURCE_SINGLE STATE observing 10\n[X4LAN] AUTH_SOURCE_SINGLE STATE done 11\n'
  with patch.object(m.client_evidence,'observe',return_value={'local_job_applied':True}):
   self.assertTrue(self.coord.verify_final({'server':source,'client':b'anything\n'}))
   for bad in (source.replace(b'STATE done 11',b'STATE done 9'),
               source.replace(b'STATE done',b'STATE observing'),
               source.replace(b'STATE done',b'STATE unknown'),source.rstrip(b'\n')):
    with self.assertRaises(ValueError):self.coord.verify_final({'server':bad,'client':b'anything\n'})
 def test_role_installs_share_world_and_job_lineage_with_distinct_ports(self):
  ticket={'world_epoch':self.coord.attempt}
  with patch.object(m.source_install,'install',return_value=[]) as source, \
       patch.object(m.client_install,'install',return_value=[]) as client:
   self.coord.install(Path('/case-a'),Path('/profile-a'),ticket,{'role':'server'},'x',120,60)
   self.coord.install(Path('/case-b'),Path('/profile-b'),ticket,{'role':'client'},'y',120,60)
  a=source.call_args.args[3];b=client.call_args.args[3]
  self.assertEqual(a['epoch'],b['epoch']);self.assertEqual(a['generation'],b['generation'])
  self.assertEqual(a['baseline'],m.archive.COUNT);self.assertEqual(b['seed'],7183)
  self.assertEqual(len({a['control_port'],a['job_port'],b['participant_port'],b['job_port']}),4)
  self.assertEqual(client.call_args.args[4],{'sector_a':1})
 def test_lifecycle_hooks_restored_without_starting_x4(self):
  with tempfile.TemporaryDirectory() as out:
   args=argparse.Namespace(window=1,out=Path(out))
   orig=(m.lifecycle.coordinator.CensusCoordinator,m.lifecycle.installer.install,m.lifecycle.owned.spawn_owned_gated,m.lifecycle.load_observation)
   with patch.object(m.lifecycle,'run',return_value={'success':False}):
    result=m.run(args)
   self.assertFalse(result['success']);self.assertFalse(result['source_activation_is_birth'])
   self.assertEqual(orig,(m.lifecycle.coordinator.CensusCoordinator,m.lifecycle.installer.install,m.lifecycle.owned.spawn_owned_gated,m.lifecycle.load_observation))


class MultiPair(unittest.TestCase):
 def test_multi_result_and_logs_fence_gaps_and_missing_witness(self):
  c=m.Coordinator({'sector_a':(1,)},defer_source_ack=True,max_events=2)
  self.addCleanup(c.cleanup_after_owned_processes)
  base=Pair().result();events=[{k:base[k] for k in ('event_sequence','index','sector_macro','macro','faction')}]
  events.append({**events[0],'event_sequence':2,'index':m.archive.COUNT+2})
  result={k:v for k,v in base.items() if k not in events[0]};result['events']=events
  c._validate_result(result);c.result=result;c.tickets['client']={}
  source=b'[X4LAN] AUTH_SOURCE_SINGLE STATE binding 10\n[X4LAN] AUTH_SOURCE_SINGLE STATE observing 10\n[X4LAN] AUTH_SOURCE_SINGLE STATE delivering 11\n[X4LAN] AUTH_SOURCE_SINGLE STATE observing 11\n[X4LAN] AUTH_SOURCE_SINGLE STATE done 12\n'
  client=(m.client_evidence.base.load.TAG.decode()+'pause_observed|x\n'+m.client_evidence.TAG+'RUNNING 10\n'+
          m.client_evidence.TAG+'LOCAL_APPLIED '+str(m.archive.COUNT+1)+' 11\n'+
          m.client_evidence.TAG+'LOCAL_APPLIED '+str(m.archive.COUNT+2)+' 12\n').encode()
  with patch.object(m.client_evidence.pair,'load_observation',return_value={'loaded':True}):
   self.assertTrue(c.verify_final({'server':source,'client':client}))
   for bad_source in (source.replace(b'STATE observing 11',b'STATE binding 11'),
                      source.replace(b'STATE observing 11',b'STATE await_go 11'),
                      source.replace(b'STATE observing 11',b'STATE delivering 11')):
    with self.assertRaises(ValueError):c.verify_final({'server':bad_source,'client':client})
   for bad in (client.replace(b'LOCAL_APPLIED 10056',b'LOCAL_APPLIED 10055'),
               client.replace(b'LOCAL_APPLIED 10056 12',b'LOCAL_APPLIED 10056 9')):
    with self.assertRaises(ValueError):c.verify_final({'server':source,'client':bad})
  for bad in ([events[0]], [events[0],{**events[1],'index':events[0]['index']}],
              [events[0],{**events[1],'sector_macro':'missing'}]):
   with self.assertRaises(ValueError):c._validate_result({**result,'events':bad})

class ContinuousPair(unittest.TestCase):
 def test_progress_preserves_completed_prefix_and_fences_bad_next(self):
  c=m.Coordinator({'sector_a':(1,)},defer_source_ack=True,continuous=True)
  self.addCleanup(c.cleanup_after_owned_processes)
  for seq in range(1,11):
   event={'event_sequence':seq,'index':m.archive.COUNT+seq,'sector_macro':'sector_a','macro':'ship_a','faction':'argon'}
   c._accept_progress({'event':'progress','completed':event},128)
  self.assertEqual(len(c.progress),10)
  bad={**event,'event_sequence':11,'index':m.archive.COUNT+11,'sector_macro':'unknown'}
  with self.assertRaises(ValueError):c._accept_progress({'event':'progress','completed':bad},128)
  self.assertEqual(len(c.progress),10)
  terminal={'event':'result','ok':True,'tcp_admitted':True,'tcp_job_receipt':True,'source_md_ack_observed':True,
            'client_md_ffi_asserted_by_owner':True,'synthetic_server_checkpoint_and_admission':True,
            'source_activation_is_birth':False,'descriptor_atomic':False,'frame_identity_proven':False,
            'snapshot_finished':True,'completed_count':10}
  c._validate_result(terminal);c.result=terminal;c.tickets['client']={}
  source=b'[X4LAN] AUTH_SOURCE_SINGLE STATE binding 10\n[X4LAN] AUTH_SOURCE_SINGLE STATE observing 10\n[X4LAN] AUTH_SOURCE_SINGLE STATE finishing 12\n[X4LAN] AUTH_SOURCE_SINGLE STATE done 12\n'
  lines=[m.client_evidence.base.load.TAG.decode()+'pause_observed|x',m.client_evidence.TAG+'RUNNING 10']
  lines += [m.client_evidence.TAG+'LOCAL_APPLIED '+str(m.archive.COUNT+seq)+' '+str(10+seq) for seq in range(1,11)]
  with patch.object(m.client_evidence.pair,'load_observation',return_value={'loaded':True}):
   self.assertTrue(c.verify_final({'server':source,'client':('\n'.join(lines)+'\n').encode()}))
   with self.assertRaises(ValueError):c.verify_final({'server':source,'client':('\n'.join(lines[:-1])+'\n').encode()})
  with self.assertRaises(ValueError):c._validate_result({**terminal,'completed_count':11})

class ProgressFraming(unittest.TestCase):
 def test_burst_over_twenty_frames_needs_no_per_byte_guard(self):
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
  values=[{'event':'progress','completed':{'event_sequence':i,'index':m.archive.COUNT+i,
           'sector_macro':'sector_a','macro':'ship_a','faction':'argon'}} for i in range(1,26)]
  b.sendall(b''.join(json.dumps(v).encode()+b'\n' for v in values))
  reader=m.ProgressFrames(a);checks=[]
  for value in values:self.assertEqual(json.loads(reader.read(time.monotonic()+2,lambda:checks.append(1))),value)
  self.assertLessEqual(len(checks),30)
 def test_buffered_frame_cannot_bypass_guard(self):
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
  b.sendall(b'first\nsecond\n');reader=m.ProgressFrames(a)
  self.assertEqual(reader.read(time.monotonic()+2,lambda:None),b'first')
  def bad():raise RuntimeError('guard failed')
  with self.assertRaises(RuntimeError):reader.read(time.monotonic()+2,bad)
  self.assertEqual(list(reader.available()),[b'second'])
 def test_terminal_frame_retains_extra_buffer_for_rejection(self):
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
  b.sendall(b'{"event":"result"}\ntrailing\n');reader=m.ProgressFrames(a)
  self.assertEqual(reader.read(time.monotonic()+2,lambda:None),b'{"event":"result"}')
  self.assertNotEqual(reader.buffer,b'')
 def test_guard_fault_recovers_queued_complete_frames_only(self):
  a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
  values=[{'event':'progress','completed':{'event_sequence':i,'index':m.archive.COUNT+i,
           'sector_macro':'sector_a','macro':'ship_a','faction':'argon'}} for i in range(1,26)]
  b.sendall(b''.join(json.dumps(v).encode()+b'\n' for v in values)+b'{"event":')
  reader=m.ProgressFrames(a);checks=[]
  def guard():
   checks.append(1)
   if len(checks)==2:raise RuntimeError('context failed')
  with self.assertRaises(RuntimeError):reader.read(time.monotonic()+2,guard)
  recovered=[json.loads(frame) for frame in reader.available()]
  self.assertEqual(recovered,values)
  coord=m.Coordinator({'sector_a':(1,)},defer_source_ack=True,continuous=True)
  self.addCleanup(coord.cleanup_after_owned_processes)
  for value in recovered:coord._accept_progress(value,len(json.dumps(value)))
  self.assertEqual(len(coord.progress),25)
  with self.assertRaises(ValueError):coord._accept_progress(recovered[-1],128)
  self.assertEqual(reader.buffer,b'{"event":')

if __name__=='__main__':unittest.main()
