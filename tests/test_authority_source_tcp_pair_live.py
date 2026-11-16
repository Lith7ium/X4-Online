"""Offline orchestration and final-evidence checks; no X4 execution."""
import argparse
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

if __name__=='__main__':unittest.main()
