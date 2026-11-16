"""Private recovery wiring and cooperative worker-stop doubles; no X4."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev'),str(ROOT/'tests')]
import authority_recovered_server_client as client
import test_authority_recovered_client_motion_install as fixtures
import test_authority_tcp_native_live as harness
import authority_tcp_native_live as native

class MotionWiring(unittest.TestCase):
 def setUp(self):fixtures.Install.setUp(self)
 def test_private_install_socket_and_redaction(self):
  participant=client.ServerClient(time.monotonic()+10,self.case,keep_worker=True)
  self.addCleanup(participant.cleanup_diagnostic)
  ticket={'world_epoch':'e'*32,'attempt_id':'f'*32}
  protected=participant.prepare_client_motion(self.case,self.profile,self.status,
   {'indices':[42,43],'generation':'3'*32,'timeout':2},ticket)
  self.assertEqual(participant.motion_sock.getsockname()[0],'127.0.0.1')
  self.assertTrue(all(p.is_file() for p in protected))
  self.assertEqual(participant.motion_worker_config['epoch'],self.status[1])
  self.assertEqual(participant.motion_worker_config['generation'],'3'*32)
  self.assertIn('authority_client_motion_indices={42,43}',(self.ui/'config.lua').read_text())
  participant.redact();self.assertIsNone(participant.motion_installation)
  self.assertNotIn(participant.motion_worker_config['lease'],(self.ui/'config.lua').read_text())
 def test_log_owner_faults(self):
  log=self.case/'engine.log';log.write_text('normal\n')
  self.assertTrue(client.ClientMotionErrorWatch(log).poll())
  for tag in ('[X4LAN] AUTH_RECOVERED_CLIENT_MOTION ERROR','[X4LAN] AUTH_PARTICIPANT ERROR',
   'Error while executing onEvent script for event: X4AuthoritySavedBaselineMotionBind.Result.',
   'Error while executing onEvent script for event: X4AuthorityReplicaMotionBind.Result.'):
   with self.subTest(tag=tag):
    log.write_text('normal\n');watch=client.ClientMotionErrorWatch(log);watch.poll()
    split=len(tag)//2
    with log.open('a') as out:out.write(tag[:split])
    watch.poll()
    with log.open('a') as out:out.write(tag[split:]+' details\n')
    with self.assertRaisesRegex(ValueError,'log fault'):watch.poll()
 def test_replaced_motion_socket_is_not_closed_by_cleanup(self):
  participant=client.ServerClient(time.monotonic()+10,self.case,keep_worker=True)
  participant.prepare_client_motion(self.case,self.profile,self.status,
   {'indices':[42,43],'generation':'3'*32,'timeout':2},{'world_epoch':'e'*32,'attempt_id':'f'*32})
  owned=participant.motion_sock;foreign=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
  try:
   participant.motion_sock=foreign
   with self.assertRaisesRegex(RuntimeError,'cleanup unconfirmed'):participant.cleanup_diagnostic()
   self.assertGreaterEqual(foreign.fileno(),0)
  finally:
   participant.motion_sock=owned;participant.cleanup_diagnostic();foreign.close()
 def test_log_replacement_and_truncation_are_refused(self):
  log=self.case/'engine.log';log.write_text('long normal line\n')
  watch=client.ClientMotionErrorWatch(log);watch.poll();log.write_text('x')
  with self.assertRaisesRegex(ValueError,'replacement'):watch.poll()
  log.write_text('another normal line\n');watch=client.ClientMotionErrorWatch(log);watch.poll()
  new=self.case/'new.log';new.write_text('another normal line\n');os.replace(new,log)
  with self.assertRaisesRegex(ValueError,'replacement'):watch.poll()

class CooperativeStop(unittest.TestCase):
 def case(self,event,keep_duplicate=False,timeout=3):
  participant=client.ServerClient(time.monotonic()+5,Path('/unused'),keep_worker=True)
  self.addCleanup(participant.cleanup_diagnostic)
  parent,child=socket.socketpair();participant.ipc=parent
  program=('import os,sys; f=int(sys.argv[1]); data=os.read(f,100); '
   'os.write(f,sys.argv[2].encode()+b"\\n") if data==b\'{"command":"stop"}\\n\' else None; os.close(f)')
  proc=subprocess.Popen([sys.executable,'-c',program,str(child.fileno()),event],pass_fds=(child.fileno(),))
  if keep_duplicate:
   duplicate=os.dup(child.fileno());self.addCleanup(os.close,duplicate)
  child.close()
  def cleanup():
   if proc.poll() is None:proc.kill()
   proc.wait(timeout=2)
  self.addCleanup(cleanup)
  pidfd=os.pidfd_open(proc.pid);self.addCleanup(os.close,pidfd);st=os.fstat(pidfd)
  helper=SimpleNamespace(proc=proc,pidfd=pidfd,_pidfd_identity=(st.st_dev,st.st_ino))
  participant.motion_worker_config={'enabled':True};participant._test_context=True
  participant._pin_motion_ipc()
  participant._pin_motion_stop(helper,lambda:participant._test_context,time.monotonic()+timeout)
  participant._active_check=lambda **_:True
  return participant,proc
 def test_stop_requires_source_then_worker_ack_and_exit(self):
  participant,proc=self.case('{"event":"stopped"}')
  with self.assertRaisesRegex(RuntimeError,'context changed'):participant.stop_motion_worker(lambda:False)
  self.assertFalse(participant.motion_stop_confirmed);self.assertIsNone(proc.poll())
  self.assertTrue(participant.stop_motion_worker(lambda:True))
  self.assertTrue(participant.motion_stop_confirmed);self.assertEqual(proc.returncode,0)
  self.assertTrue(participant.check_motion_stopped())
  participant._test_context=False
  with self.assertRaisesRegex(RuntimeError,'context changed'):participant.check_motion_stopped()
  with self.assertRaises(RuntimeError):participant.stop_motion_worker(lambda:True)
 def test_failed_worker_receipt_never_confirms_stop(self):
  participant,_=self.case('{"event":"failed"}')
  with self.assertRaisesRegex(RuntimeError,'unconfirmed'):participant.stop_motion_worker(lambda:True)
  self.assertFalse(participant.motion_stop_confirmed)
 def test_open_duplicate_prevents_confirmed_ipc_eof(self):
  participant,proc=self.case('{"event":"stopped"}',keep_duplicate=True,timeout=.2)
  with self.assertRaises((RuntimeError,TimeoutError)):participant.stop_motion_worker(lambda:True)
  self.assertEqual(proc.wait(timeout=1),0)
  self.assertFalse(participant.motion_stop_confirmed)
 def test_callback_cannot_replace_ipc_or_helper_process(self):
  for target in ('ipc','process','pidfd'):
   with self.subTest(target=target):
    participant,proc=self.case('{"event":"stopped"}')
    helper=participant._motion_helper;old_ipc=participant.ipc;old_pidfd=helper.pidfd
    foreign,other=socket.socketpair()
    try:
     def tamper():
      if target=='ipc':participant.ipc=foreign
      elif target=='process':helper.proc=object()
      else:helper.pidfd=os.dup(old_pidfd)
      return True
     with self.assertRaisesRegex(RuntimeError,'ownership changed'):participant.stop_motion_worker(tamper)
     self.assertFalse(participant.motion_stop_confirmed);self.assertIsNone(proc.poll());self.assertGreaterEqual(foreign.fileno(),0)
    finally:
     if target=='pidfd' and helper.pidfd!=old_pidfd:os.close(helper.pidfd)
     participant.ipc=old_ipc;helper.proc=proc;helper.pidfd=old_pidfd
     foreign.close();other.close()
 def test_cleanup_does_not_close_replaced_ipc(self):
  participant,_=self.case('{"event":"stopped"}')
  owned=participant.ipc;foreign,peer=socket.socketpair()
  try:
   def replace():participant.ipc=foreign;return True
   with self.assertRaisesRegex(RuntimeError,'ownership changed'):participant.stop_motion_worker(replace)
   with self.assertRaisesRegex(RuntimeError,'cleanup unconfirmed'):participant.cleanup_diagnostic()
   self.assertGreaterEqual(foreign.fileno(),0)
   foreign.sendall(b'x');self.assertEqual(peer.recv(1),b'x')
  finally:
   participant.ipc=owned;foreign.close();peer.close()

class FourthFD(unittest.TestCase):
 def test_retained_worker_gets_exclusive_motion_fd_after_initial_pause(self):
  # Real coordinator/worker and sockets, simulated X4/control receipts only.
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'store').mkdir();(root/'client/save').mkdir(parents=True)
   (root/'game').mkdir();(root/'game/X4').symlink_to('/proc/self/exe')
   store=harness.CheckpointStore(root/'store');service=harness.FileService('f'*32,slots=(1,)).start()
   engine=harness.FreshEngine(root);engine._timeout=5
   world=harness.WorldCoordinator('a'*32,engine,store,harness.SaveOffers(service,store))
   p=native.TCPMarkedParticipant(time.monotonic()+15,first_resume_only=True,keep_worker=True)
   udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0));udp.settimeout(.05)
   p.motion_sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);p.motion_sock.bind(('127.0.0.1',0))
   p._pin_motion_socket()
   st=os.fstat(p.motion_sock.fileno());identity_fd=(st.st_dev,st.st_ino)
   p.motion_worker_config={'lease':'1'*32,'attempt':'2'*32,'epoch':'3'*32,'generation':'4'*32,'timeout':1}
   stop=threading.Event();commands=[];destination=p.sock.getsockname();thread=None
   def fake():
    while not stop.is_set():
     udp.sendto(('HELLO|'+p.lease+'|'+'a'*32).encode(),destination)
     try:data,peer=udp.recvfrom(1024)
     except socket.timeout:continue
     except OSError:return
     row=data.decode().split('|')
     if len(row)==5 and row[0]=='CMD':
      _,lease,epoch,number,op=row;commands.append(op)
      udp.sendto('|'.join(('RECEIPT',lease,epoch,number,op,'confirmed')).encode(),peer)
   try:
    handle=p.join(world);world.step();world.step()
    ticket,target=p.offer_and_download(world,service,handle,root,root/'client')
    identity=(os.getpid(),native.marked.base.live.start_ticks(os.getpid()))
    thread=threading.Thread(target=fake);thread.start();result={}
    with unittest.mock.patch.object(p,'verify_logs'), unittest.mock.patch.object(native.marked.base.client,'game_identity',return_value=identity):
     p.on_ready(world=world,handle=handle,ticket=ticket,target=target,server_identity=identity,server_proc=object(),
      server_started=identity[1],client_identity=identity,client_proc=object(),client_started=identity[1],
      game=root/'game',out=root,deadline=time.monotonic()+10,result=result,check_protected=lambda:True)
    self.assertTrue(result['helper_active']);self.assertEqual(commands,['pause','resume']);self.assertIsNone(p.motion_sock)
    fds=Path('/proc')/str(p.helpers[-1].proc.pid)/'fd';found=[]
    for fd in fds.iterdir():
     try:s=fd.stat()
     except FileNotFoundError:continue
     if (s.st_dev,s.st_ino)==identity_fd:found.append(fd)
    self.assertEqual(len(found),1)
   finally:
    p.cleanup_before_owned_processes();stop.set();udp.close()
    if thread is not None:thread.join(2)
    service.close();service.thread.join(2)
if __name__=='__main__':unittest.main()
