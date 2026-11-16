"""Explicit one-peer diagnostic incarnation binding over real local TCP."""
import unittest
from unittest.mock import patch
from tests import test_authority_experimental_tcp_participants as fixture
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_participants import ExperimentalTCPParticipants

class TestIncarnation(unittest.TestCase):
 def pair(self):
  case=fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation');case.setUp();self.addCleanup(case.doCleanups)
  peer=case.connect();case.offer_and_claim(peer);case.responder(peer);case.host.tick(.1)
  return case,peer,ExperimentalTCPJobDelivery(case.host,enabled=True,timeout=1)
 def test_opt_in_binds_only_actual_connection_once(self):
  case,_,delivery=self.pair();self.assertTrue(delivery.bind_test_incarnation(1,'b'*32,enabled=True))
  self.assertEqual(delivery.membership(),({'id':'peer_1','incarnation':'b'*32},))
  with self.assertRaises(ValueError):delivery.bind_test_incarnation(1,'b'*32,enabled=True)
  self.assertTrue(case.host._failed)
 def test_disabled_does_not_affect_legacy_minting(self):
  case,_,delivery=self.pair()
  with self.assertRaises(ValueError):delivery.bind_test_incarnation(1,'b'*32)
  result=delivery.membership();self.assertEqual(result[0]['id'],'peer_1');self.assertNotEqual(result[0]['incarnation'],'b'*32)
  self.assertFalse(case.host._failed)
 def test_existing_minted_identity_cannot_be_overwritten(self):
  case,_,delivery=self.pair();before=delivery.membership()
  with self.assertRaises(ValueError):delivery.bind_test_incarnation(1,'b'*32,enabled=True)
  self.assertEqual(delivery._incarnations[1],before[0]['incarnation']);self.assertTrue(case.host._failed)
 def test_foreign_handle_or_malformed_token_fences(self):
  for handle,token in ((2,'b'*32),(1,'bad')):
   with self.subTest(handle=handle):
    case,_,delivery=self.pair()
    with self.assertRaises(ValueError):delivery.bind_test_incarnation(handle,token,enabled=True)
    self.assertTrue(case.host._failed);self.assertEqual(delivery._incarnations,{})
 def test_disconnected_peer_fences_without_regeneration(self):
  case,peer,delivery=self.pair();delivery.bind_test_incarnation(1,'b'*32,enabled=True);peer.shutdown(2)
  with self.assertRaises(RuntimeError):delivery.membership()
  self.assertTrue(case.host._failed);self.assertEqual(delivery._incarnations,{1:'b'*32})
 def test_swallowed_reentrant_binding_fences(self):
  case,_,delivery=self.pair()
  def attack(*args):
   try:delivery.bind_test_incarnation(1,'b'*32,enabled=True)
   except RuntimeError:pass
  with patch.object(ExperimentalTCPParticipants,'_quiet',side_effect=attack):
   with self.assertRaises(RuntimeError):delivery.bind_test_incarnation(1,'b'*32,enabled=True)
  self.assertTrue(case.host._failed);self.assertEqual(delivery._incarnations,{})
 def test_reentry_during_second_quiet_never_publishes_binding(self):
  case,_,delivery=self.pair();original=ExperimentalTCPParticipants._quiet;calls=[]
  def attack(*args):
   calls.append(1)
   if len(calls)==2:
    try:delivery.bind_test_incarnation(1,'b'*32,enabled=True)
    except RuntimeError:pass
   return original(*args)
  with patch.object(ExperimentalTCPParticipants,'_quiet',side_effect=attack):
   with self.assertRaises(RuntimeError):delivery.bind_test_incarnation(1,'b'*32,enabled=True)
  self.assertEqual(len(calls),2);self.assertTrue(case.host._failed);self.assertEqual(delivery._incarnations,{})
 def test_replaced_peer_object_fences_without_regeneration(self):
  case,_,delivery=self.pair();delivery.bind_test_incarnation(1,'b'*32,enabled=True)
  conn,peer=next(iter(case.control._peers.items()));case.control._peers[conn]=dict(peer)
  with self.assertRaises(RuntimeError):delivery.membership()
  self.assertTrue(case.host._failed);self.assertEqual(delivery._incarnations,{1:'b'*32})
 def test_multi_participant_not_permitted(self):
  case=fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation');case.setUp();self.addCleanup(case.doCleanups)
  a=case.connect();b=case.connect();case.offer_and_claim(a);case.offer_and_claim(b);case.responder(a);case.responder(b);case.host.tick(.1)
  delivery=ExperimentalTCPJobDelivery(case.host,enabled=True,timeout=1)
  with self.assertRaises(ValueError):delivery.bind_test_incarnation(1,'b'*32,enabled=True)
  self.assertTrue(case.host._failed);self.assertEqual(delivery._incarnations,{})
if __name__=='__main__':unittest.main()
