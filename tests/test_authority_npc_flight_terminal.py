"""Synthetic lifecycle checks: no X4, real network, or user save."""
import importlib.util
from pathlib import Path
import time
import types
import unittest
import tempfile
import threading
import sys

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('terminal_flight',ROOT/'tools/dev/authority_npc_flight_terminal.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class TerminalTest(unittest.TestCase):
    def test_real_local_offer_is_withdrawn_and_service_stops(self):
        sys.path.insert(0,str(ROOT/'src'))
        from authority.save_transfer import SaveOffers
        from authority.checkpoints import CheckpointStore
        from lockstep.launcher.joinfiles import FileService
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'save.xml.gz';path.write_bytes(b'isolated-checkpoint')
            service=FileService('a'*32,slots=(1,)).start()
            service.offer('j1.xml.gz',path)
            offers=SaveOffers(service,CheckpointStore(Path(temp)));offers.names.add('j1.xml.gz')
            world=types.SimpleNamespace(session=types.SimpleNamespace(state='paused',pending=None,ready_players=()))
            engine=types.SimpleNamespace(resume=lambda:None,pause=lambda:None)
            control=module.TerminalControl(world=world,engine=engine,offers=offers,service=service,
                                           check_processes=lambda:True,deadline=time.monotonic()+10,bridge_timeout=1)
            errors=[]
            def begin():
                try: control.begin()
                except Exception as error: errors.append(error)
            thread=threading.Thread(target=begin,daemon=True);thread.start();thread.join(timeout=3)
            self.assertFalse(thread.is_alive(),'real service fence did not finish')
            self.assertEqual(errors,[])
            self.assertEqual(control.state,'fenced')
            self.assertEqual(offers.names,set())
            self.assertNotIn('j1.xml.gz',service.offered)
            self.assertFalse(service.thread.is_alive())

    def make(self,*,state='paused',pending=None,ready=(),check=lambda:True,fail_resume=False):
        calls=[]
        class Engine:
            def resume(self):
                calls.append('resume')
                if fail_resume: raise TimeoutError('ambiguous native state')
            def pause(self): calls.append('pause')
        offers=types.SimpleNamespace(invalidate=lambda:calls.append('invalidate'))
        service=types.SimpleNamespace(close=lambda:calls.append('close'))
        world=types.SimpleNamespace(session=types.SimpleNamespace(state=state,pending=pending,ready_players=ready))
        return module.TerminalControl(world=world,engine=Engine(),offers=offers,service=service,
                                     check_processes=check,deadline=time.monotonic()+60,bridge_timeout=1),calls

    def test_fence_resume_source_stop_pause_order_is_one_shot(self):
        terminal,calls=self.make();terminal.begin();terminal.resume()
        with self.assertRaises(RuntimeError): terminal.pause()
        terminal.source_stopped();terminal.pause()
        self.assertEqual(calls,['invalidate','close','resume','pause'])
        with self.assertRaises(RuntimeError): terminal.resume()

    def test_ambiguous_resume_faults_and_refuses_retry(self):
        terminal,calls=self.make(fail_resume=True);terminal.begin()
        with self.assertRaises(TimeoutError): terminal.resume()
        self.assertEqual(terminal.state,'failed')
        with self.assertRaises(RuntimeError): terminal.resume()
        self.assertEqual(calls,['invalidate','close','resume'])

    def test_nonquiescent_or_changed_process_does_not_resume(self):
        for options in ({'state':'running'},{'pending':'save'},{'ready':('one',)},{'check':lambda:False}):
            terminal,calls=self.make(**options)
            with self.subTest(options=options),self.assertRaises(RuntimeError): terminal.begin()
            self.assertNotIn('resume',calls)
            self.assertEqual(terminal.state,'failed')
