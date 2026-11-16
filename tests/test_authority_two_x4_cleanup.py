"""Focused supervisor ownership tests; harmless gate helper only, no X4."""
from contextlib import ExitStack
from pathlib import Path
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_two_x4_live as supervisor


class SpawnSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)

    def simulated_spawn(self, mode):
        processes=[];proc=Mock(pid=123);proc.poll.return_value=None;handlers={};released=[]
        def change_signal(number,handler):
            old=handlers.get(number,supervisor.signal.SIG_DFL)
            if mode=='restore_signal' and number==supervisor.signal.SIGTERM and handler==supervisor.signal.SIG_DFL:
                old(number,None)
            handlers[number]=handler;return old
        def popen(*args,**kwargs):
            self.assertTrue(kwargs['start_new_session'])
            self.assertEqual(len(kwargs['pass_fds']),1)
            if mode=='popen_signal': handlers[supervisor.signal.SIGTERM](supervisor.signal.SIGTERM,None)
            return proc
        def write_gate(fd,data):
            released.append(data)
            if mode=='gate_signal': handlers[supervisor.signal.SIGTERM](supervisor.signal.SIGTERM,None)
            return 1
        def start_ticks(_):
            if mode=='identity_failure': raise RuntimeError('identity unavailable')
            return 7
        with patch.object(supervisor.signal,'signal',side_effect=change_signal), \
             patch.object(supervisor.subprocess,'Popen',side_effect=popen), \
             patch.object(supervisor.live,'start_ticks',side_effect=start_ticks), \
             patch.object(supervisor.os,'write',side_effect=write_gate):
            if mode in ('popen_signal','gate_signal','restore_signal'):
                with self.assertRaises(InterruptedError):
                    supervisor.spawn_owned_gated(['unused'],self.path/'log',processes)
            else:
                with self.assertRaises(RuntimeError):
                    supervisor.spawn_owned_gated(['unused'],self.path/'log',processes)
        self.assertEqual(len(processes),1);self.assertIs(processes[0][0],proc)
        self.assertEqual(processes[0][1],None if mode=='identity_failure' else 7)
        self.assertEqual(released,[b'G'] if mode in ('gate_signal','restore_signal') else [])
        self.assertTrue(all(v==supervisor.signal.SIG_DFL for v in handlers.values()))

    def test_signal_during_popen_keeps_gate_closed(self): self.simulated_spawn('popen_signal')
    def test_signal_at_gate_write_leaves_tracked_process(self): self.simulated_spawn('gate_signal')
    def test_signal_during_handler_restore_leaves_tracked_process(self): self.simulated_spawn('restore_signal')
    def test_missing_start_identity_keeps_gate_closed(self): self.simulated_spawn('identity_failure')

    def test_exec_gate_runs_only_after_recorded_start_identity(self):
        processes=[]
        proc,started=supervisor.spawn_owned_gated([sys.executable,'-c','pass'],self.path/'real-log',processes)
        self.assertEqual(processes,[[proc,started]])
        self.assertEqual(proc.wait(timeout=5),0)


class VerificationContextTests(unittest.TestCase):
    def test_checks_identities_on_both_sides_of_hashes(self):
        target=Path('/private/save');config=Path('/private/config')
        params=dict(deadline=20,server_proc='server',server_started=1,server_identity=('s',1),
                    client_proc='client',client_started=2,client_identity=('c',2),game='game',
                    home='home',uid=1000,steam='steam',target=target,ticket={'sha256':'save'},
                    expected={config:'config'})
        identities=lambda proc,*_:('s',1) if proc=='server' else ('c',2)
        hashes=lambda path:'save' if path==target else 'config'
        with patch.object(supervisor.time,'monotonic',side_effect=[10,11]), \
             patch.object(supervisor.client,'game_identity',side_effect=identities), \
             patch.object(supervisor.live,'steam_identity',return_value='steam'), \
             patch.object(supervisor.live,'sha',side_effect=hashes):
            self.assertTrue(supervisor.check_live_context(**params))
        with patch.object(supervisor.time,'monotonic',side_effect=[10,21]), \
             patch.object(supervisor.client,'game_identity',side_effect=identities), \
             patch.object(supervisor.live,'steam_identity',return_value='steam'), \
             patch.object(supervisor.live,'sha',side_effect=hashes):
            with self.assertRaises(RuntimeError): supervisor.check_live_context(**params)
        with patch.object(supervisor.time,'monotonic',return_value=10), \
             patch.object(supervisor.client,'game_identity',side_effect=[('s',1),('c',2),('s',1),('changed',3)]), \
             patch.object(supervisor.live,'steam_identity',return_value='steam'), \
             patch.object(supervisor.live,'sha',side_effect=hashes):
            with self.assertRaises(RuntimeError): supervisor.check_live_context(**params)
        with patch.object(supervisor.time,'monotonic',return_value=10), \
             patch.object(supervisor.client,'game_identity',side_effect=identities), \
             patch.object(supervisor.live,'steam_identity',return_value='steam'), \
             patch.object(supervisor.live,'sha',return_value='changed'):
            with self.assertRaises(ValueError): supervisor.check_live_context(**params)


class FileServiceStartupTests(unittest.TestCase):
    def simulate_start(self, mode):
        services=[];handlers={};service=Mock();service.thread=None
        def change_signal(number,handler):
            old=handlers.get(number,supervisor.signal.SIG_DFL)
            if mode=='restore_signal' and number==supervisor.signal.SIGTERM and handler==supervisor.signal.SIG_DFL:
                old(number,None)
            handlers[number]=handler
            return old
        def construct(*_a,**_k):
            if mode=='construct_signal': handlers[supervisor.signal.SIGTERM](supervisor.signal.SIGTERM,None)
            return service
        def start():
            if mode in ('thread_signal','restore_signal','thread_failure'):
                service.thread=Mock();service.thread.is_alive.side_effect=[True,False]
            if mode=='thread_signal': handlers[supervisor.signal.SIGTERM](supervisor.signal.SIGTERM,None)
            if mode in ('start_failure','thread_failure'): raise RuntimeError('start failed')
            return service
        service.start.side_effect=start
        with patch.object(supervisor.signal,'signal',side_effect=change_signal), \
             patch.object(supervisor.joinfiles,'FileService',side_effect=construct):
            if mode in ('construct_signal','thread_signal','restore_signal'):
                with self.assertRaises(InterruptedError): supervisor.start_owned_file_service('a'*32,services)
            else:
                with self.assertRaises(RuntimeError): supervisor.start_owned_file_service('a'*32,services)
        self.assertEqual(services,[service]);self.assertTrue(all(v==supervisor.signal.SIG_DFL for v in handlers.values()))
        supervisor.close_owned_file_service(service)
        if mode in ('construct_signal','start_failure'):
            service.close.assert_not_called();service.server.server_close.assert_called_once()
        else:
            service.close.assert_called_once();service.thread.join.assert_called_once_with(timeout=2)

    def test_signal_during_constructor_registers_before_aborting(self): self.simulate_start('construct_signal')
    def test_signal_during_start_registers_started_service(self): self.simulate_start('thread_signal')
    def test_signal_during_restore_registers_started_service(self): self.simulate_start('restore_signal')
    def test_start_failure_before_thread_does_not_call_shutdown(self): self.simulate_start('start_failure')
    def test_start_failure_after_thread_still_cleans_up(self): self.simulate_start('thread_failure')

    def test_unstarted_real_listener_closes_without_shutdown(self):
        service=supervisor.joinfiles.FileService('a'*32,slots=(1,))
        with patch.object(service.server,'shutdown',side_effect=AssertionError('must not call shutdown')):
            supervisor.close_owned_file_service(service)
        self.assertEqual(service.server.fileno(),-1)


class SupervisorCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def run_failing(self, survivor=False, service_failure=False, steam_change=False, system_exit=False, helper_failure=False):
        game=self.root/'game';(game/'extensions').mkdir(parents=True);(game/'X4').touch()
        auth=self.root/'auth';auth.touch();out=self.root/'out';lock_path=self.root/'owned-lock';lock_path.touch()
        lock_fd=os.open(lock_path,os.O_RDONLY);lock_stat=object()
        first,second=Mock(pid=111),Mock(pid=222)
        args=SimpleNamespace(out=out,game=game,display=':0',timeout=60,seed=1)
        user=SimpleNamespace(pw_dir=str(self.root),pw_uid=1000,pw_gid=1000,pw_name='tester')
        fake_sock=Mock();fake_sock.getsockname.return_value=('127.0.0.1',12345);handlers={};steam=('stable',)
        def change_signal(number,handler): handlers[number]=handler;return supervisor.signal.SIG_DFL
        def prepare(out_dir,_game,_home):
            case=out_dir/'case';profile=case/'profile';(profile/'save').mkdir(parents=True)
            return case,profile,[],case/'lock'
        def spawn(_command,_log,processes):
            # Simulate a supervisor that already owns two children when a later
            # operation fails; the second fails cleanup, the first must still stop.
            processes.extend([[first,1],[second,2]])
            return first,1
        def stop(proc,started):
            if service_failure: return []
            if proc is second:
                if survivor: return [222]
                raise KeyboardInterrupt('stop failure')
            return []
        with ExitStack() as stack:
            def set_(obj,name,value): return stack.enter_context(patch.object(obj,name,value))
            set_(supervisor.os,'geteuid',lambda:1000)
            stack.enter_context(patch.dict(supervisor.os.environ,{'XAUTHORITY':str(auth)}))
            set_(supervisor.snapshot,'output_path',lambda _:out)
            set_(supervisor.live,'sha',lambda _:supervisor.live.EXE_SHA)
            set_(supervisor.live,'x4_executables',lambda:[]);set_(supervisor.shutil,'which',lambda _: '/bin/bwrap')
            set_(supervisor.pwd,'getpwuid',lambda _:user)
            steam_check=set_(supervisor.live,'steam_identity',Mock(side_effect=[steam,('changed',)])
                             if steam_change else Mock(return_value=steam))
            set_(supervisor.snapshot,'prepare_case',prepare)
            config=out/'server/case/extensions/x4_lan_lab/ui/config.lua'
            original='authority_control_lease="'+'a'*32+'"\n'
            def install(*_):
                config.parent.mkdir(parents=True);config.write_text(original)
            set_(supervisor.server,'install_probe',install)
            set_(supervisor.socket,'socket',lambda *a,**k:fake_sock)
            set_(supervisor.live,'create_lock_target',lambda *_:(lock_fd,lock_stat))
            release=set_(supervisor.live,'release_lock_target',Mock(side_effect=lambda *_:os.close(lock_fd)))
            set_(supervisor.signal,'signal',side_effect_signal:=Mock(side_effect=change_signal))
            set_(supervisor.snapshot,'command_for',lambda *_:['unused'])
            set_(supervisor,'spawn_owned_gated',spawn)
            fake_service=Mock();fake_service.thread=Mock();fake_service.thread.is_alive.return_value=True
            if service_failure:
                set_(supervisor.secrets,'token_hex',lambda *_:'a'*32)
                fake_sock.recvfrom.return_value=(('HELLO|'+'a'*32+'|'+'a'*32).encode(),('127.0.0.1',4567))
                set_(supervisor.client,'game_identity',Mock(return_value=('server',1)))
                set_(supervisor,'LocalControlBridge',Mock())
                def start_service(_token,services): services.append(fake_service);return fake_service
                set_(supervisor,'start_owned_file_service',start_service)
                set_(supervisor,'WorldCoordinator',Mock(side_effect=KeyboardInterrupt('run failure')))
                fake_service.close.side_effect=KeyboardInterrupt('close failure')
            else:
                error=SystemExit('run failure') if system_exit else KeyboardInterrupt('run failure')
                set_(supervisor.client,'game_identity',Mock(side_effect=error))
            stop_mock=set_(supervisor.snapshot,'stop_owned',Mock(side_effect=stop))
            def fail_helper():
                if helper_failure == 'interrupt': raise KeyboardInterrupt('helper cleanup')
                return False
            experiment=SimpleNamespace(cleanup_before_owned_processes=fail_helper) if helper_failure else None
            if system_exit:
                with self.assertRaises(SystemExit): supervisor.run(args)
                import json
                result=json.loads((out/'result.json').read_text())
            else: result=supervisor.run(args,experiment=experiment)
        self.assertFalse(result['success']);self.assertEqual(result['owned_cleanup_confirmed'],service_failure)
        self.assertTrue(lock_path.exists())
        if service_failure:
            self.assertIn('service cleanup failed',result['cleanup_error']);release.assert_called_once()
            fake_service.close.assert_called_once();fake_service.server.server_close.assert_called_once()
            self.assertEqual(config.read_text(),'authority_control_lease="redacted"\n')
        else:
            self.assertIn('lock retained',result['cleanup_error']);release.assert_not_called()
            self.assertEqual(config.read_text(),original)
            self.assertIn('server config retained',result['cleanup_error'])
        if steam_change:
            self.assertEqual(result['error'],'run failure');self.assertIn('Steam identity changed',result['cleanup_error'])
        if system_exit: self.assertEqual(result['error'],'run failure')
        if helper_failure:
            stop_mock.assert_not_called()
            self.assertIsNone(result['owned_processes_remaining'])
            self.assertIn('helper cleanup unconfirmed',result['cleanup_error'])
        elif not survivor and not service_failure:
            self.assertIsNone(result['owned_processes_remaining'])
        else:
            self.assertEqual(stop_mock.call_count,2)
            self.assertEqual(stop_mock.call_args_list[0].args,(second,2))
            self.assertEqual(stop_mock.call_args_list[1].args,(first,1))
        self.assertTrue((out/'result.json').is_file());self.assertGreaterEqual(steam_check.call_count,2)
        self.assertTrue(all(value==supervisor.signal.SIG_DFL for value in handlers.values()))
        fake_sock.close.assert_called_once()

    def test_stop_baseexception_does_not_skip_other_cleanup(self): self.run_failing()
    def test_surviving_process_retains_lock(self): self.run_failing(survivor=True)
    def test_service_close_exception_does_not_skip_process_cleanup(self): self.run_failing(service_failure=True)
    def test_steam_change_preserves_original_error(self): self.run_failing(steam_change=True)
    def test_system_exit_remains_failure_and_propagates(self): self.run_failing(system_exit=True)
    def test_unconfirmed_helper_retains_processes_and_lock(self): self.run_failing(helper_failure=True)
    def test_interrupted_helper_cleanup_retains_processes_and_lock(self): self.run_failing(helper_failure='interrupt')


if __name__=='__main__': unittest.main()
