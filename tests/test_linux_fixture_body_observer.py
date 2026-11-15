"""Synthetic LuaJIT/getter and sealed-overlay checks; never execute native X4."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import struct
import tempfile
import unittest
from unittest import mock

from lupa.luajit21 import LuaRuntime, LuaError
from test_stock_keyboard_replay_overlay import snapshot_bytes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import build_native_gate_overlay as builder
import linux_gate_live as live
import linux_semaphore_observer_bundle as bundle

MODULE = 'native_gate_fixture_body_observer.lua'
SOURCE = (ROOT / 'tools/dev' / MODULE).read_text()
PROBE = (ROOT / 'tools/dev/native_gate_probe.lua').read_text()


class FixtureBodyLuaTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute('''
            ffi=require('ffi')
            ffi.cdef('typedef struct {float x,y,z,yaw,pitch,roll;} UIPosRot;')
            cfg={native_gate_fixture_body_observe=true,native_gate_hash='battle',
                native_gate_snapshot_sha=string.rep('a',64),native_gate_snapshot_fixture={}}
            for i=1,12 do cfg.native_gate_snapshot_fixture[i]=string.format('%016x',i) end
            events={};logs={};reads=0;gets=0
            local function forbidden() error('simulation-capable diagnostic called') end
            gate={platform=function() return 'linux' end,actor=forbidden,params_build=forbidden,
                shield_refresh=forbidden,body=function(actor,which)
                    assert(actor==6);reads=reads+1
                    events[#events+1]='body'..which
                    return 'pose='..reads
                end}
            function emit(s) events[#events+1]='log';logs[#logs+1]=s end
            position=ffi.new('UIPosRot',{1.25,2.5,-3.75,0.824562013,-0.5,0.145146161})
            function getter() gets=gets+1;events[#events+1]='getter';return position end
        ''')
        self.lua.execute(SOURCE)

    def create(self):
        self.lua.execute('observer=X4LAN_FIXTURE_BODY_OBSERVER.create(cfg,gate,emit)')

    def test_full_probe_compiles_in_actual_luajit(self):
        # This catches the real chunk's local/upvalue limits without loading C.
        self.lua.eval('function(s) assert(loadstring(s)) end')(PROBE)

    def test_single_original_getter_adjacent_reads_then_logs_preserve_bits(self):
        self.create()
        self.lua.execute('returned=observer.sample(1513,6,getter);assert(returned==position)')
        values = self.lua.globals()
        self.assertEqual(list(values.events.values()),
                         ['body0', 'body1', 'getter', 'body0', 'body1'] + ['log'] * 5)
        self.assertEqual((values.reads, values.gets), (4, 1))
        logs = list(values.logs.values())
        expected = struct.pack('<6f', 1.25, 2.5, -3.75, 0.824562013, -0.5, 0.145146161).hex()
        self.assertIn('raw=' + expected, logs[2])
        self.assertIn('phase=before which=0 raw=pose=1', logs[0])
        self.assertIn('phase=after which=0 raw=pose=3', logs[3])
        self.assertTrue(all('actor=6 saved=0000000000000006' in s for s in logs))

    def test_real_struct_array_reads_embedded_zero_bytes_without_ffi_string(self):
        self.create()
        self.lua.execute('''
            -- The native game truncated the binary ffi.string path. Reject any
            -- use here, retaining real cdata allocation, casts and byte reads.
            ffi.string = function() error('binary ffi.string is forbidden') end
            local array = ffi.new('UIPosRot[1]')
            array[0] = position
            getter = function() return array[0] end
            assert(observer.sample(1400, 6, getter) == array[0])
        ''')
        expected = struct.pack('<6f', 1.25, 2.5, -3.75, 0.824562013, -0.5, 0.145146161).hex()
        self.assertIn('00', expected)
        recorded = self.lua.globals().logs[3].split('raw=', 1)[1]
        self.assertEqual(len(recorded), 48)
        self.assertEqual(recorded, expected)

    def test_bounded_window_and_no_default_interaction(self):
        self.create()
        for tick, actor, wanted in ((1399,6,False),(1400,6,True),(1600,6,True),(1601,6,False),(1513,5,False)):
            self.assertEqual(self.lua.globals().observer.wanted(tick,actor), wanted)
        with self.assertRaises(LuaError):
            self.lua.execute('observer.sample(1601,6,getter)')
        for value in ('nil','false'):
            self.lua.execute('cfg.native_gate_fixture_body_observe='+value+';assert(X4LAN_FIXTURE_BODY_OBSERVER.create(cfg,{},nil)==nil)')
        self.assertEqual(self.lua.globals().reads, 0)

    def test_admission_and_mutating_diagnostics_fail_closed(self):
        for mutation in ("cfg.native_gate_fixture_body_observe=1", "gate.platform=function() return 'windows' end",
                         'gate.body=nil', 'cfg.native_gate_snapshot_sha=nil', 'cfg.native_gate_snapshot_fixture[6]=nil',
                         "cfg.native_gate_snapshot_fixture[6]='0000000000000000'", 'cfg.native_gate_actor_diag=true',
                         'cfg.native_gate_shield_refresh=true', "cfg.native_gate_hash='clock'"):
            with self.subTest(mutation=mutation):
                self.setUp()
                self.lua.execute(mutation)
                with self.assertRaises(LuaError): self.create()
                self.assertEqual(self.lua.globals().reads,0)

    def test_missing_malformed_and_absent_body_not_normalized(self):
        for raw in ('nil', "''", "string.rep('x',1025)", "'bad\\nrow'"):
            with self.subTest(raw=raw):
                self.setUp();self.create()
                self.lua.execute('gate.body=function() return '+raw+' end')
                with self.assertRaises(LuaError): self.lua.execute('observer.sample(1513,6,getter)')
                self.assertEqual(self.lua.globals().gets,0)
                self.assertEqual(len(self.lua.globals().logs),0)
        # Native reader's literal none/gone are observations, never fabricated poses.
        self.setUp();self.create()
        self.lua.execute("gate.body=function(_,which) return which==0 and 'none' or 'gone' end;observer.sample(1513,6,getter)")
        self.assertIn('raw=none', self.lua.globals().logs[1])
        self.assertIn('raw=gone', self.lua.globals().logs[2])

    def enable_body_steps(self):
        self.lua.execute('''
            cfg.native_gate_body_step_diag=true
            step_tick=1400;step_count='8';step_failures='0';step_calls=0
            step_seq0='18446744073709551610';step_seq1='18446744073709551611'
            function step_record()
                return 'steps='..step_count..' dt=3ccccccd collision=1 seq0='..step_seq0..
                    ' seq1='..step_seq1..' body0='..string.rep('12345678',32)..
                    ' motion0='..string.rep('bc663933',32)..' body1='..string.rep('90abcdef',32)..
                    ' motion1='..string.rep('bc663937',32)
            end
            gate.body_step=function(actor,which)
                assert(actor==6);step_calls=step_calls+1;events[#events+1]='step'..which
                return step_record()
            end
            gate.body_step_status=function()
                events[#events+1]='step_status'
                return 'tick='..step_tick..' installed=1 restored=0 updates=20 captured=40 failures='..
                    step_failures..' state=1 pin=1 stage=armed'
            end
        ''')
        self.create()

    def test_body_steps_explicit_drain_then_qualified_without_changing_getter(self):
        self.enable_body_steps()
        self.lua.execute('observer.sample(1400,6,getter);step_tick=1401;step_count="1";step_seq0="18446744073709551612";step_seq1="18446744073709551613";observer.sample(1401,6,getter)')
        logs=list(self.lua.globals().logs.values())
        self.assertIn('qualified=0 reason=initial_drain',logs[6])
        self.assertIn('qualified=1 reason=complete failures=0',logs[14])
        self.assertIn('pose0='+'12345678'*8+' pose1='+'90abcdef'*8,logs[14])
        self.assertIn('motion0='+'bc663933'*32,logs[14])
        self.assertIn('seq0=18446744073709551612 seq1=18446744073709551613',logs[14])
        self.assertEqual((self.lua.globals().gets,self.lua.globals().reads,self.lua.globals().step_calls),(2,8,4))
        events=list(self.lua.globals().events.values())
        self.assertEqual(events[:5],['body0','body1','getter','body0','body1'])
        self.assertLess(events.index('body1'),events.index('step0'))

    def test_body_step_bad_missing_accumulated_failed_stale_and_gap_are_unqualified(self):
        cases=(('step_count="0"','step_count_unqualified'),
               ('step_count="2"','step_count_unqualified'),
               ('step_failures="1"','status_unqualified'),
               ('step_tick=1400','status_unqualified'),
               ('gate.body_step_status=function() return nil end','status_unqualified'),
               ('step_seq1=step_seq0','sequence_unqualified'),
               ('step_seq0="18446744073709551616"','missing_or_malformed'),
               ('gate.body_step=function() return nil end','missing_or_malformed'),
               ('gate.body_step=function() return string.rep("a",2401) end','missing_or_malformed'),
               ('gate.body_step=function() return "bad"..string.char(0).."record" end','missing_or_malformed'),
               ('gate.body_step=function() return "bad\\nrecord" end','missing_or_malformed'))
        for mutation,reason in cases:
            with self.subTest(mutation=mutation):
                self.setUp();self.enable_body_steps()
                self.lua.execute('observer.sample(1400,6,getter);step_tick=1401;step_count="1";'+mutation+';observer.sample(1401,6,getter)')
                logs=list(self.lua.globals().logs.values())
                self.assertIn('qualified=0 reason='+reason,logs[14])
                self.assertFalse(any('qualified=1' in row for row in logs))
                self.assertEqual(self.lua.globals().gets,2)
        self.setUp();self.enable_body_steps()
        self.lua.execute('observer.sample(1400,6,getter);step_tick=1402;step_count="1";observer.sample(1402,6,getter)')
        self.assertIn('qualified=0 reason=sample_gap',self.lua.globals().logs[15])

    def test_body_steps_repeated_sequence_is_unqualified_then_requires_fresh_baseline(self):
        self.enable_body_steps()
        self.lua.execute('''
            observer.sample(1400,6,getter)
            step_tick=1401;step_count='1';observer.sample(1401,6,getter)
            step_tick=1402;step_seq0='18446744073709551612';step_seq1='18446744073709551613'
            observer.sample(1402,6,getter)
            step_tick=1403;step_seq0='18446744073709551614';step_seq1='18446744073709551615'
            observer.sample(1403,6,getter)
        ''')
        logs=list(self.lua.globals().logs.values())
        self.assertIn('qualified=0 reason=sequence_regression',logs[14])
        self.assertIn('qualified=0 reason=sequence_baseline',logs[22])
        self.assertIn('qualified=1 reason=complete',logs[30])
        self.assertEqual(self.lua.globals().gets,4)

    def test_body_steps_missing_explicit_readers_rejected_and_false_stays_inert(self):
        self.lua.execute('cfg.native_gate_body_step_diag=true')
        with self.assertRaises(LuaError): self.create()
        self.lua.execute('cfg.native_gate_body_step_diag="on"')
        with self.assertRaises(LuaError): self.create()
        self.lua.execute('''
            cfg.native_gate_body_step_diag=false
            gate.body_step=function() error('unexpected step read') end
            gate.body_step_status=function() error('unexpected status read') end
        ''')
        self.create();self.lua.execute('observer.sample(1513,6,getter)')
        self.assertEqual(len(self.lua.globals().logs),5)

    def test_actual_probe_getter_row_identical_off_on_and_outside_window(self):
        sample = PROBE[PROBE.index('local function sample(tick)'):]
        fragment = sample[sample.index('   local since=profile and gate.qpc_us()\n   local p\n'):]
        fragment = fragment[:fragment.index('   if native then row[2]')]
        self.create()
        self.lua.execute('''
            realffi=ffi;ffi={C={GetObjectPositionInSector=getter}}
            function GetComponentData() return 91.25,82.5 end
            i=6;object={};profile=nil
        ''')
        rows=[]
        for enabled,tick in ((False,1513),(True,1513),(True,1399),(True,1601)):
            self.lua.execute(f'fixture_body_observer={"observer" if enabled else "nil"};tick={tick}')
            self.lua.execute(fragment)
            rows.append(self.lua.globals().row[1])
        self.assertEqual(rows,[rows[0]]*4)
        self.assertEqual((self.lua.globals().gets,self.lua.globals().reads),(4,4))


class FixtureBodyPackagingTests(unittest.TestCase):
    def build(self, enabled=True, extra=()):
        root=Path(self.directory.name)
        snapshot=root/'save.gz';snapshot.write_bytes(snapshot_bytes())
        gate=root/'gate.so';gate.write_bytes(b'synthetic gate')
        output=root/f'out{len(list(root.iterdir()))}'
        arguments=['overlay','--gate-so',str(gate),'--snapshot',str(snapshot),
                   '--out',str(output),'--mode','battle','--snapshot-prebind','--world-identities','--serial-pathing',
                   *(['--fixture-body-observe'] if enabled else []),*extra]
        with mock.patch.object(sys,'argv',arguments),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            builder.main()
        return output

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)

    def test_default_off_and_explicit_hash_bound_module_before_probe(self):
        for enabled in (False,True):
            out=self.build(enabled)
            config=(out/'ui/config.lua.append').read_text()
            self.assertEqual('native_gate_fixture_body_observe = true' in config,enabled)
            self.assertNotIn('native_gate_actor_diag = true',config)
            self.assertNotIn('native_gate_shield_refresh = true',config)
            self.assertEqual((out/'ui'/MODULE).exists(),enabled)
            if enabled:
                files=(out/'ui.xml.files').read_text().splitlines()
                self.assertLess(files.index('ui/'+MODULE),files.index('ui/native_gate_probe.lua'))
                manifest=json.loads((out/'x4lane-manifest.json').read_text())
                for name in ('ui/'+MODULE,'ui/native_gate_probe.lua','ui/config.lua.append'):
                    self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),manifest[name])

    def test_explicit_existing_body_step_flag_does_not_enable_actor_diagnostics(self):
        out=self.build(extra=('--body-step-diag',))
        config=(out/'ui/config.lua.append').read_text()
        self.assertIn('native_gate_fixture_body_observe = true',config)
        self.assertIn('native_gate_body_step_diag = true',config)
        self.assertNotIn('native_gate_actor_diag = true',config)
        self.assertNotIn('native_gate_shield_refresh = true',config)

    def test_mutating_diagnostic_conflicts_including_implicit_actor_enable(self):
        for flag in ('--actor-diag','--body-diag','--shield-refresh','--params-init','--strict-state','--flight-diag'):
            with self.subTest(flag=flag),self.assertRaises(SystemExit): self.build(extra=(flag,))

    def test_missing_prebinding_or_wrong_mode_rejected(self):
        for args in (('--mode','clock'),):
            with self.subTest(args=args),self.assertRaises(SystemExit): self.build(extra=args)
        # Module also enforces runtime snapshot registration; builder requires explicit prebinding.
        with mock.patch.object(sys,'argv',['overlay','--fixture-body-observe','--snapshot','/unused',
                '--gate-so','/unused','--mode','battle','--out',str(Path(self.directory.name)/'missing')]), \
                contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit): builder.main()

    def test_outer_bundle_forwards_option_and_seals_helper(self):
        root=Path(self.directory.name);snapshot=root/'save.gz';snapshot.write_bytes(snapshot_bytes())
        out=root/'bundle';forwarded=[]
        def command(arguments,**kwargs):
            if 'build_native_gate_linux.py' in str(arguments[1]):
                (out/'.build/x4lan_gate.so').write_bytes(b'synthetic gate')
            elif 'build_native_gate_overlay.py' in str(arguments[1]):
                forwarded.extend(arguments)
                with mock.patch.object(sys,'argv',arguments[1:]): builder.main()
            return mock.Mock(stdout='fixture-commit\n' if 'rev-parse' in arguments else '',returncode=0)
        with mock.patch.object(live.subprocess,'run',side_effect=command),contextlib.redirect_stdout(io.StringIO()):
            live.main(['bundle','--zig','/unused','--snapshot',str(snapshot),'--out',str(out),
                       '--ticks','1800','--battle','--serial-pathing','--path-determinism','1','--fixture-body-observe'])
        self.assertIn('--fixture-body-observe',forwarded)
        manifest=json.loads((out/'manifest.json').read_text())
        self.assertTrue(manifest['fixture_body_observe'])
        name='extension/x4_lan_lab/ui/'+MODULE
        self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),manifest['files'][name])
        for source in ('tools/dev/'+MODULE, 'tools/dev/build_native_gate_overlay.py',
                       'tests/test_linux_fixture_body_observer.py'):
            key='source-receipts/'+source
            self.assertEqual(hashlib.sha256((out/key).read_bytes()).hexdigest(),manifest['files'][key])
        # Exercise actual admission: changed frozen observation source must fail.
        receipt=out/'source-receipts/tools/dev'/MODULE
        receipt.write_bytes(receipt.read_bytes()+b'-- changed\n')
        with self.assertRaisesRegex(ValueError,'changed semaphore source'):
            bundle.validate_bundle(out,dict(manifest,view_query_source_version=bundle.SOURCE_VERSION),True)
        # Exact closure is required for frozen launch receipts, including the test.
        paths=bundle.source_paths(ROOT)
        self.assertIn(ROOT/'tools/dev'/MODULE,paths)
        self.assertIn(Path(__file__).resolve(),paths)
        with mock.patch.object(bundle,'SOURCES',('tools/dev/missing-observer.lua',)),self.assertRaises(ValueError):
            bundle.source_paths(ROOT)


if __name__=='__main__': unittest.main()
