"""Fake-process runner lifecycle; no X4 or census archive."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import os
import tempfile
import unittest
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_census_replica_live as m


class Runner(unittest.TestCase):
    def test_three_process_resource_gate(self):
        with tempfile.TemporaryDirectory() as t,ExitStack() as stack:
            root=Path(t);cg=root/'cgroup';child=cg/'user'/'task';child.mkdir(parents=True)
            for p in (cg/'user',child):
                (p/'memory.max').write_text('max');(p/'memory.current').write_text('0')
            mem=root/'meminfo';mem.write_text(f'MemAvailable: {20*1024**2} kB\n')
            membership=root/'membership';membership.write_text('0::/user/task\n')
            stack.enter_context(patch.object(m,'_MEMINFO',mem));stack.enter_context(patch.object(m,'_CGROUP_MEMBERSHIP',membership))
            stack.enter_context(patch.object(m,'_CGROUP_ROOT',cg))
            disk=stack.enter_context(patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=3*1024**3)))
            m.check_three_process_resources(root,3)
            (cg/'user'/'memory.max').write_text(str(9*1024**3))
            with self.assertRaisesRegex(RuntimeError,'insufficient'):m.check_three_process_resources(root,3)
            (cg/'user'/'memory.max').write_text('max')
            (cg/'memory.max').write_text(str(9*1024**3));(cg/'memory.current').write_text('0')
            with self.assertRaisesRegex(RuntimeError,'insufficient'):m.check_three_process_resources(root,3)
            (cg/'memory.max').write_text('max');disk.return_value=SimpleNamespace(free=1)
            with self.assertRaisesRegex(RuntimeError,'insufficient'):m.check_three_process_resources(root,3)
            membership.write_text('0::/../outside\n')
            with self.assertRaisesRegex(RuntimeError,'invalid cgroup'):m.check_three_process_resources(root,3)

    def test_load_marker_pause_evidence_requires_order_and_no_fault(self):
        ticket={'world_epoch':'a'*32,'connection_handle':1,'baseline_id':1,'load_generation':1,
                'checkpoint_id':m.archive.CHECKPOINT_ID,'sha256':m.archive.SHA256,'attempt_id':'b'*32,'slot':'save_009'}
        fields='|'.join(str(ticket[k]) for k in m.base.load.FIELDS)
        load=m.base.load.TAG.decode();marker='[X4LAN] AUTH_MARKER load '
        rows=[load+'load_requested|'+fields,marker+'INSPECTED '+m.archive.MARKER,load+'pause_observed|'+fields]
        raw=lambda values:('\n'.join(values)+'\n').encode()
        self.assertTrue(m.load_observation(raw(rows),ticket)['initial_pause_checked'])
        self.assertIsNone(m.load_observation(raw(rows[:2]),ticket,partial=True))
        for bad in ([rows[1],rows[0],rows[2]],rows+[rows[2]],rows+['[X4LAN] AUTH_CENSUS_JOB ERROR FAULT'],
                    rows+['Invalid data types for arithmetic operation!']):
            with self.subTest(bad=bad),self.assertRaises(ValueError):m.load_observation(raw(bad),ticket,partial=True)

    def simulate(self,mode):
        with tempfile.TemporaryDirectory() as t,ExitStack() as stack:
            root=Path(t);game=root/'game';(game/'extensions').mkdir(parents=True);(game/'X4').write_bytes(b'')
            auth=root/'auth';auth.write_bytes(b'');store=root/'old'/'checkpoints';store.mkdir(parents=True)
            witness=root/'witness.json';witness.write_bytes(b'');out=root/'new'
            args=SimpleNamespace(out=out,store=store,timeout=300,window=30,seed=1,game=game,display=':0')
            args.two_clients=mode.startswith('multi_')
            args.defer_source_ack=mode.startswith(('deferred_','saved_')) or args.two_clients
            if mode.startswith('saved_'):args.saved_index=41
            user=SimpleNamespace(pw_dir=str(root),pw_uid=1000,pw_gid=1000,pw_name='tester')
            set_=lambda obj,name,value:stack.enter_context(patch.object(obj,name,value))
            set_(m.os,'geteuid',lambda:1000);stack.enter_context(patch.dict(m.os.environ,{'XAUTHORITY':str(auth)}))
            def resources(_,remaining):
                if mode=='multi_low_resources' and remaining==2:raise RuntimeError('insufficient resources')
            resource_check=set_(m,'check_three_process_resources',Mock(side_effect=resources))
            set_(m.base.snapshot,'output_path',lambda _:out);set_(m.base.base,'local_directory',lambda _:store)
            set_(m.census,'ensure_separate',lambda *_:None);set_(m.inputs,'WITNESS_PATH',witness)
            set_(m.base.live,'EXE_SHA','fake');set_(m.base.live,'sha',lambda _:'fake')
            set_(m.shutil,'which',lambda _:'/bin/bwrap');set_(m.base.live,'x4_executables',lambda:[])
            set_(m.pwd,'getpwuid',lambda _:user);late_steam=[False]
            set_(m.base.live,'steam_identity',lambda *_:('changed',) if late_steam[0] else ('stable',))
            fps={'archive':'stable'};set_(m.archive,'fingerprints',lambda _:fps)
            verified=SimpleNamespace(witness_candidates={},archive_fingerprints=fps,witness_sha256='a'*64)
            handlers={}
            def verify(_):
                if mode=='signal_verify':handlers[m.signal.SIGTERM](m.signal.SIGTERM,None)
                return verified
            ver=set_(m.inputs,'verify_once',Mock(side_effect=verify))
            def prepare(roleout,*_):
                case=roleout/'case';profile=case/'profile';(profile/'save').mkdir(parents=True)
                return case,profile,[],case/'lock'
            set_(m.base.snapshot,'prepare_case',prepare);set_(m.census,'origin_scripts',lambda *_:None)
            staged_fp=(1,2,4,5,6);staged_targets={}
            def stage(_,profiles):
                out={}
                for role,p in profiles.items():
                    target=p/'save'/'save_009.xml.gz';target.write_bytes(b'save');out[role]=(target,staged_fp,m.archive.SHA256);staged_targets[role]=target
                return out
            staging=set_(m.inputs,'stage_three' if args.two_clients else 'stage_pair',Mock(side_effect=stage));set_(m.installer,'_BASE_MD',())
            installed=[]
            def install(_,__,___,config,*rest):
                installed.append(dict(config))
                if mode=='swap_before_first' and config['role']=='client':staged_targets['server'].write_bytes(b'changed')
                return []
            set_(m.installer,'install',install)
            set_(m.readonly,'readonly_save_command',lambda *_:['bwrap','--die-with-parent'])
            def stable(path,*_,**kw):
                raw=b'Invalid data types for arithmetic operation!' if mode=='no_event_final_md_error' and path.name=='engine-output.log' else b'log'
                return (staged_fp,m.archive.SHA256,raw)
            def read_live(*_):
                raw=b'Could not find suitable data type for conversion!' if mode=='live_md_error' else b'log'
                return raw,((1,2),3,b'digest')
            set_(m.base,'stable_read',stable);set_(m.base,'read_live_log',read_live)
            set_(m.base,'log_continuity',lambda *_:None)
            real_observation=m.load_observation
            def observe(raw,*_,**__):
                if mode=='final_fault' and raw==b'log-final':raise ValueError('late fault')
                if raw!=b'log':return real_observation(raw,{})
                return {'initial_pause_checked':True}
            set_(m,'load_observation',observe)
            coord=Mock();coord.attempt='a'*32;coord.replica_dispatch_attempted=False
            coord.add_role.side_effect=lambda role:{'role':'server' if role=='server' else 'client'}
            def run(context):
                assert context['check']() is True
                if mode.startswith('saved_'):
                    details={'saved_baseline_registered':True,'saved_index':41,'motion_client_bound_buffered':True,
                             'motion_pose_applied':False,'checkpoint_identity_proven':False,'frame_identity_proven':False}
                    if mode=='saved_bad':details['ship_creation_requested']=True
                    return details
                if mode.startswith('no_event'):
                    raise m.coordinator.NoNewRegistryEntry('no new registry entry observed')
                coord.replica_dispatch_attempted=True
                if mode=='dispatch_uncertain':raise RuntimeError('replica dispatch outcome uncertain')
                details={'tcp_ack_after_client_replica':True,'ship_creation_requested':True,'artificial_seed':7183}
                if mode in ('deferred_ok','multi_ok','multi_missing_client'):details['source_queue_acked']=True
                if mode=='multi_ok':details['clients_confirmed']=['client1','client2']
                return details
            coord.run.side_effect=run
            coord.cleanup_before_owned_processes.return_value=mode not in ('helper_failure','multi_helper_failure')
            def post_cleanup():
                if mode=='no_event_steam_error':late_steam[0]=True
                return mode!='no_event_udp_error'
            coord.cleanup_after_owned_processes.side_effect=post_cleanup
            coord.verify_final.return_value=mode!='final_fault'
            coord.verify_no_event_final.return_value=mode!='no_event_bad_final'
            set_(m.coordinator,'CensusCoordinator',lambda _,**kw:coord)
            set_(m.multi_coordinator,'MultiCensusCoordinator',lambda _:coord)
            def sig(number,handler):handlers[number]=handler;return m.signal.SIG_DFL
            set_(m.signal,'signal',sig)
            lockfile=root/'lock';lockfile.write_bytes(b'')
            def lock(*_):return os.open(lockfile,os.O_RDONLY),'lockstat'
            set_(m.base.live,'create_lock_target',lock)
            def release_lock(_,fd,__):
                os.close(fd)
                if mode=='no_event_lock_error':raise RuntimeError('release unconfirmed')
            release=set_(m.base.live,'release_lock_target',Mock(side_effect=release_lock))
            procs=[]
            def spawn(_,__,owned):
                proc=Mock(pid=100+len(procs));procs.append(proc);owned.append([proc,7])
                if mode=='swap_before_second' and len(procs)==1:staged_targets['client'].write_bytes(b'changed')
                if mode=='signal_second' and len(procs)==2:handlers[m.signal.SIGTERM](m.signal.SIGTERM,None)
                return proc,7
            set_(m.owned,'spawn_owned_gated',spawn)
            def identity(proc,*_):
                if mode=='multi_client2_crash' and proc.pid==102:raise RuntimeError('client2 lost')
                if mode=='multi_alias':return (100,7,1,2)
                return (proc.pid,7,1,2)
            set_(m.base.load,'game_identity',identity)
            def stop(proc,_):
                if mode=='stop_error' and proc.pid==100:raise RuntimeError('unknown')
                return []
            stopping=set_(m.base.snapshot,'stop_owned',Mock(side_effect=stop))
            result=m.run(args)
            ver.assert_called_once_with(store)
            self.assertTrue((out/'result.json').is_file())
            if mode=='signal_verify':
                staging.assert_not_called();self.assertEqual(procs,[]);release.assert_not_called();return result
            staging.assert_called_once()
            expected_processes=0 if mode=='swap_before_first' else 1 if mode in ('swap_before_second','multi_low_resources') else 3 if args.two_clients else 2
            self.assertEqual(len(procs),expected_processes)
            self.assertEqual(stopping.call_count,0 if mode in ('helper_failure','multi_helper_failure') else expected_processes)
            if args.defer_source_ack and not args.two_clients:
                self.assertEqual(installed,[{'role':'server','defer_source_ack':True},{'role':'client'}])
            if args.two_clients:
                self.assertEqual(installed,[{'role':'server','defer_source_ack':True},{'role':'client'},{'role':'client'}])
                self.assertGreaterEqual(resource_check.call_count,2)
            else:resource_check.assert_not_called()
            if mode in ('ok','deferred_ok','multi_ok','saved_ok'):
                self.assertTrue(result['success']);self.assertTrue(result['owned_cleanup_confirmed'])
                self.assertEqual(result['owned_processes_remaining'],[]);release.assert_called_once()
                self.assertEqual(result['ship_creation_requested'],mode!='saved_ok');self.assertFalse(result['multiplayer_proven'])
            else:
                self.assertFalse(result['success'])
                if mode=='dispatch_uncertain':self.assertTrue(result['ship_creation_requested'])
                if mode=='no_event':self.assertEqual(result.get('classification'),'inconclusive_no_new_registry_entry')
                elif mode.startswith('no_event'):self.assertNotIn('classification',result)
                if mode in ('helper_failure','multi_helper_failure','stop_error'):
                    self.assertIsNone(result['owned_processes_remaining']);release.assert_not_called()
                    self.assertIn('lock retained: stop unconfirmed',result['cleanup_errors'])
                else:release.assert_called_once()
            return result

    def test_lifecycle_and_fencing(self):
        for mode in ('ok','deferred_ok','deferred_missing_ack','saved_ok','saved_bad','multi_ok','multi_missing_client','multi_helper_failure','multi_client2_crash','multi_alias','multi_low_resources','signal_verify','signal_second','helper_failure','stop_error','final_fault','swap_before_first','swap_before_second',
                     'no_event','no_event_bad_final','no_event_udp_error','no_event_lock_error','no_event_steam_error',
                     'live_md_error','no_event_final_md_error','dispatch_uncertain'):
            with self.subTest(mode=mode):self.simulate(mode)

if __name__=='__main__':unittest.main()
