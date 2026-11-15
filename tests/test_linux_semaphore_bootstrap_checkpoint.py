"""Fixed-prefix evidence and actual native/provider adapters; no game launch."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest import mock

from linux_player_network_evidence import parse_network_physics_evidence, collect_network_physics_evidence
import linux_gate_live as live
import linux_semaphore_observer_bundle as bundle
from test_linux_t40_evidence import common_trace

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / 'src/native/engine/linux'
CHECKPOINT = 'X4LAN SEMAPHORE OBSERVER CHECKPOINT tick=399 owner=77 main_parked=1 complete=1\n'


def prefix_trace(count=420, checkpoint=399):
    rows, stderr, engine = common_trace(count)
    result = []
    tick = None
    for row in rows:
        match = re.search(r'physics=frame tick=([0-9]+) event=begin', row)
        if match:
            tick = int(match[1])
            if tick == 37:
                result.append('X4LAN WORKER_DISPATCH bootstrap=1 parked=1 count=0 maximum=1\n')
            result.append(f'X4LAN WORKER_DISPATCH tick={tick} ticket={tick} consumed=1 post_returned=1\n')
        result.append(row)
        boundary = 'physics=upkeep stage=leave ' in row
        if tick == checkpoint and boundary:
            result.append(CHECKPOINT.replace('tick=399', f'tick={checkpoint}'))
    return result, stderr, engine


class BootstrapCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.stderr, cls.engine = prefix_trace()

    def parse(self, rows, tick=399):
        return parse_network_physics_evidence(rows, self.stderr, self.engine, 223,
            frame_count=420, slot=2, session_frames=420, startup='v1-t40',
            allow_semaphore_checkpoint=True, allow_worker_dispatch=True,
            bootstrap_checkpoint_tick=tick)

    def test_exact_prefix_and_dispatch_after_closure(self):
        result = self.parse(self.rows)
        self.assertTrue(result['pass'], result['errors'][:8])
        self.assertEqual(result['semaphore_checkpoint']['tick'], 399)
        self.assertEqual(result['frames'][-1]['tick'], 459)
        self.assertFalse(self.parse(self.rows, tick=None)['pass'])
        for checkpoint in (37, 38, 39, 459):
            rows, _, _ = prefix_trace(checkpoint=checkpoint)
            with self.subTest(checkpoint=checkpoint):
                proof = self.parse(rows, tick=checkpoint)
                self.assertTrue(proof['pass'], proof['errors'][:8])
                if checkpoint < 40:
                    self.assertEqual([frame['tick'] for frame in proof['preapply_frames']], [37, 38, 39])
                    self.assertEqual(proof['semaphore_checkpoint']['tick'], checkpoint)
                    index = rows.index(CHECKPOINT.replace('tick=399', f'tick={checkpoint}'))
                    self.assertIn('physics=upkeep stage=leave ', rows[index - 1])
                    self.assertIn('snapshot=physics_end ', rows[index + 1])

    def test_duplicate_outside_wrong_position_and_lost_later_ticket(self):
        index = self.rows.index(CHECKPOINT)
        cases = [self.rows[:index] + [CHECKPOINT] + self.rows[index:],
                 self.rows[:index-1] + [CHECKPOINT] + self.rows[index-1:index] + self.rows[index+1:],
                 [row for row in self.rows if not row.startswith('X4LAN WORKER_DISPATCH tick=400 ')],
                 [row.replace('tick=400 ticket=400', 'tick=400 ticket=399') for row in self.rows]]
        for rows in cases:
            self.assertFalse(self.parse(rows)['pass'])
        for tick in (True, '399', 399.0, -1, 36, 460, 1 << 64):
            self.assertFalse(self.parse(self.rows, tick=tick)['pass'])

    def test_failure_retains_exact_raw_trace(self):
        broken = [row for row in self.rows if not row.startswith('X4LAN WORKER_DISPATCH tick=400 ')]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            trace, retained, stderr, engine, output = [directory / name for name in ('trace', 'retained', 'stderr', 'engine', 'output')]
            for path, rows in ((trace, broken), (stderr, self.stderr), (engine, self.engine), (output, [])):
                path.write_text(''.join(rows))
            result = collect_network_physics_evidence(trace, retained, engine, output, 223,
                frame_count=420, stderr=stderr, slot=2, session_frames=420, startup='v1-t40',
                allow_semaphore_checkpoint=True, allow_worker_dispatch=True, bootstrap_checkpoint_tick=399)
            self.assertFalse(result['pass'])
            self.assertEqual(trace.read_bytes(), retained.read_bytes())

    def test_manifest_admission_environment_and_runner_forwarding(self):
        options = {'semaphore_observer': True, 'worker_dispatch': True, 'bootstrap_checkpoint_tick': 399,
                   'player_ui_session_frames': 420, 'independent_keyboard_frames': 420,
                   'player_startup_phases': 'v1-t40', 'serial_pathing': True, 'mass_traffic': 'sync',
                   'player_lifetime_preload': True, 'semaphore_observer_sha256': 'a'*64,
                   'semaphore_observer_size': 1}
        self.assertTrue(bundle.enabled(options))
        for value in (True, '399', 399.0, -1, 36, 460, 1 << 64):
            with self.assertRaises(ValueError):
                bundle.enabled(dict(options, bootstrap_checkpoint_tick=value))
        for name in ('worker_dispatch', 'semaphore_observer'):
            with self.assertRaises(ValueError):
                bundle.enabled(dict(options, **{name: False}))
        for value, expected in ((399, '399'), (None, None)):
            env, _ = bundle.wrap_program(Path('/case'), dict(options, bootstrap_checkpoint_tick=value),
                {'X4_DEV_SEMAPHORE_BOOTSTRAP_TICK': '123'}, ['/case/game/X4'])
            self.assertEqual(env.get('X4_DEV_SEMAPHORE_BOOTSTRAP_TICK'), expected)
        with mock.patch.object(live, 'bundle') as build:
            live.main(['bundle', '--snapshot', '/unused', '--out', '/unused', '--zig', '/unused',
                       '--bootstrap-checkpoint-tick', '399'])
            self.assertEqual(build.call_args.args[0].bootstrap_checkpoint_tick, 399)
        with tempfile.TemporaryDirectory() as directory:
            stderr = Path(directory) / 'stderr'
            stderr.write_text('')
            with mock.patch.object(live, 'collect_network_physics_evidence',
                                   return_value={'pass': True, 'errors': [], 'stderr_sha256': live.sha(stderr)}) as collect:
                live.collect_network_client((), stderr, 420, 2, allow_semaphore_checkpoint=True,
                                            allow_worker_dispatch=True, bootstrap_checkpoint_tick=399)
            self.assertEqual(collect.call_args.kwargs['bootstrap_checkpoint_tick'], 399)

    def test_actual_provider_checkpoint_then_resident_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'checkpoint'
            subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
                str(ENGINE / 'test_player_semaphore_dispatch_checkpoint.c'), '-o', str(executable)], check=True, timeout=30)
            subprocess.run([str(executable)], check=True, timeout=10)

    def test_actual_native_checkpoint_configuration_and_tail(self):
        text = (ENGINE / 'gate_player_control_recurring.h').read_text()
        def function(signature):
            start = text.index(signature)
            end = text.index('{', start) + 1
            depth = 1
            while depth:
                depth += (text[end] == '{') - (text[end] == '}')
                end += 1
            return text[start:end]
        tail = function('static void player_recurring_tail_callback(void *semaphore, unsigned count) {')
        self.assertIn('(player_semaphore_checkpoint_prefix || getenv("X4MP_SEMAPHORE_OBSERVER"))', tail)
        self.assertLess(tail.index('player_recurring_checkpoint_tail(generation);'),
                        tail.index('player_physics_network_finish(generation,'))
        source = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>
static unsigned player_dispatch_enabled = 1, player_semaphore_checkpoint_done;
static unsigned player_semaphore_checkpoint_prefix;
static uint64_t player_semaphore_checkpoint_tick;
typedef struct { uint64_t take; } test_startup_phase;
static test_startup_phase phase = {37};
static test_startup_phase *player_startup(void) { return &phase; }
static int entered = 1, calls, complete = 1, owner_ok = 1, rows;
static int player_recurring_physics_entered(void) { return entered; }
static _Noreturn void player_recurring_fatal(const char *reason) {
    if (!strcmp(reason, "semaphore_checkpoint_incomplete")) assert(calls == 1 && rows == 1);
    _exit(42);
}
static int fake_checkpoint(uint64_t tick) { assert(tick >= 37 && tick <= 459); ++calls; return complete; }
static int (*x4mp_semaphore_observer_checkpoint)(uint64_t) = fake_checkpoint;
static int player_semaphore_pinned_provider(void *symbol, Dl_info *owner) {
    (void)symbol; owner->dli_fbase = (void *)1; return 1;
}
static void *fake_dlsym(void *handle, const char *name) { (void)handle; (void)name; return (void *)2; }
static int fake_dladdr(void *symbol, Dl_info *owner) { (void)symbol; owner->dli_fbase = (void *)(uintptr_t)owner_ok; return 1; }
#define dlsym fake_dlsym
#define dladdr fake_dladdr
static void lifecycle_discard_write(const char *text) { assert(strstr(text, "CHECKPOINT")); ++rows; }
'''
        source += function('static void player_recurring_checkpoint_configure(') + '\n'
        source += function('static void player_recurring_checkpoint_tail(') + '\n'
        source += r'''
static void expect_child(pid_t child, int code) {
    assert(child >= 0);
    int status;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == code);
}
int main(void) {
    assert(!setenv("X4MP_SEMAPHORE_OBSERVER", "1", 1));
    const char *invalid[] = {"", "0", "0399", "36", "460", "399x", "-399", "+399", " 399", "18446744073709551616"};
    for (unsigned test = 0; test < sizeof invalid / sizeof *invalid; ++test) {
        pid_t child = fork(); assert(child >= 0);
        if (!child) { player_recurring_checkpoint_configure(invalid[test], 459); _exit(99); }
        expect_child(child, 42);
    }
    const char *valid[] = {"37", "38", "39", "399", "459", NULL};
    for (unsigned test = 0; test < sizeof valid / sizeof *valid; ++test) {
        pid_t child = fork(); assert(child >= 0);
        if (!child) {
            player_recurring_checkpoint_configure(valid[test], 459);
            uint64_t expected = valid[test] ? strtoull(valid[test], NULL, 10) : 459;
            assert(player_semaphore_checkpoint_tick == expected);
            assert(player_semaphore_checkpoint_prefix == (valid[test] != NULL));
            player_recurring_checkpoint_tail(expected - 1); assert(!calls);
            player_recurring_checkpoint_tail(expected);
            player_recurring_checkpoint_tail(expected + 1);
            assert(calls == 1 && rows == 1 && player_semaphore_checkpoint_done);
            _exit(0);
        }
        expect_child(child, 0);
    }
    for (unsigned test = 0; test < 14; ++test) {
        pid_t child = fork(); assert(child >= 0);
        if (!child) {
            if (test == 10) unsetenv("X4MP_SEMAPHORE_OBSERVER");
            if (test == 11) setenv("X4MP_SEMAPHORE_OBSERVER", "0", 1);
            if (test == 12) player_dispatch_enabled = 0;
            player_recurring_checkpoint_configure(test == 13 ? NULL : "399", 459);
            if (test == 0 || test == 4 || test == 13) unsetenv("X4_DEV_SEMAPHORE_BOOTSTRAP_TICK");
            if (test == 1 || test == 5) setenv("X4_DEV_SEMAPHORE_BOOTSTRAP_TICK", "459", 1);
            if (test <= 1 || test == 13) complete = 0;
            if (test == 2) unsetenv("X4MP_SEMAPHORE_OBSERVER");
            if (test == 3) setenv("X4MP_SEMAPHORE_OBSERVER", "0", 1);
            if (test == 7) owner_ok = 0;
            if (test == 8) entered = 0;
            if (test == 9) x4mp_semaphore_observer_checkpoint = NULL;
            uint64_t tick = test == 13 ? 459 : 399;
            player_recurring_checkpoint_tail(tick);
            if (test == 6) player_recurring_checkpoint_tail(tick);
            assert(calls == 1 && rows == 1 && player_semaphore_checkpoint_done);
            _exit(0);
        }
        /* Default final-only incomplete reporting is unchanged; explicit prefixes fail immediately. */
        expect_child(child, test == 4 || test == 5 || test == 13 ? 0 : 42);
    }
}
'''
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            path = directory / 'checkpoint.c'
            path.write_text(source)
            subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', str(path),
                            '-o', str(directory / 'checkpoint')], check=True, timeout=30)
            subprocess.run([str(directory / 'checkpoint')], check=True, timeout=10)
