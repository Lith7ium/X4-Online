"""Synthetic /proc fixtures; no live game process or profiling tools."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from authority.linux_proc_sampler import LinuxProcSampler, ProcessObservationError


def stat_line(pid, name, user, system, start):
    # Fields following comm begin with field 3 (state).
    fields = ['S'] + ['0'] * 19
    fields[11], fields[12], fields[19] = str(user), str(system), str(start)
    return f'{pid} ({name}) ' + ' '.join(fields) + '\n'


class Clock:
    def __init__(self):
        self.now = 0.0
    def __call__(self):
        return self.now
    def sleep(self, duration):
        self.now += duration


class LinuxProcSamplerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.proc = Path(self.temporary.name)
        self.clock = Clock()
        self.process(101, 10, 100, 5, 1200)
        self.thread(101, 101, 10, 60, 4, 'main ) thread')
        self.thread(101, 102, 20, 40, 1, 'worker')
        self.process(201, 30, 20, 0, 500)
        self.thread(201, 201, 30, 20, 0, 'supervisor')
        self.sampler = LinuxProcSampler({'server': (101, 10), 'supervisor': (201, 30)},
                                       proc_root=self.proc, clock=self.clock, clock_ticks=100)

    def process(self, pid, start, user, system, rss_kib):
        path = self.proc / str(pid)
        (path / 'task').mkdir(parents=True, exist_ok=True)
        (path / 'stat').write_text(stat_line(pid, f'process {pid}', user, system, start))
        (path / 'status').write_text(f'Name:\ttest\nVmRSS:\t{rss_kib} kB\n')

    def thread(self, pid, tid, start, user, system, name):
        path = self.proc / str(pid) / 'task' / str(tid)
        path.mkdir(parents=True, exist_ok=True)
        (path / 'stat').write_text(stat_line(tid, name, user, system, start))

    def test_cpu_and_rss_are_separate_per_process_and_thread(self):
        baseline = self.sampler.sample()
        self.assertIsNone(baseline['processes']['server']['cpu_percent'])
        self.assertIsNone(baseline['processes']['server']['threads'][0]['cpu_percent'])
        self.clock.now = 1.0
        self.process(101, 10, 225, 30, 1300)
        self.thread(101, 101, 10, 140, 24, 'main ) thread')
        self.thread(101, 102, 20, 85, 6, 'worker')
        self.process(201, 30, 22, 1, 600)
        self.thread(201, 201, 30, 22, 1, 'supervisor')
        result = self.sampler.sample()
        server = result['processes']['server']
        self.assertEqual(server['cpu_percent'], 150.0)
        self.assertEqual(server['rss_bytes'], 1300 * 1024)
        self.assertEqual([t['cpu_percent'] for t in server['threads']], [100.0, 50.0])
        self.assertEqual(server['threads'][0]['name'], 'main ) thread')
        self.assertEqual(result['processes']['supervisor']['cpu_percent'], 3.0)
        self.assertNotIn('fps', result)

    def test_new_exited_and_reused_tid_are_not_given_false_rates(self):
        self.sampler.sample()
        (self.proc / '101/task/101/stat').unlink()
        self.thread(101, 102, 99, 2, 0, 'replacement')
        self.thread(101, 103, 40, 4, 0, 'new')
        self.clock.now = 1
        process = self.sampler.sample()['processes']['server']
        self.assertEqual(process['threads_unreadable'], [101])
        self.assertEqual(process['threads_no_longer_observed'],
                         [{'tid': 101, 'start_ticks': 10}, {'tid': 102, 'start_ticks': 20}])
        self.assertEqual([thread['cpu_percent'] for thread in process['threads']], [None, None])

    def test_changed_or_disappeared_process_fences_sampler(self):
        self.sampler.sample()
        self.process(101, 11, 1, 0, 1200)
        self.clock.now = 1
        with self.assertRaisesRegex(ProcessObservationError, 'identity changed'):
            self.sampler.sample()
        self.process(101, 10, 100, 5, 1200)
        with self.assertRaisesRegex(ProcessObservationError, 'fenced'):
            self.sampler.sample()

    def test_disappeared_process_does_not_yield_a_partial_result(self):
        self.sampler.sample()
        (self.proc / '201/stat').unlink()
        self.clock.now = 1
        with self.assertRaisesRegex(ProcessObservationError, 'cannot sample process 201'):
            self.sampler.sample()
        with self.assertRaisesRegex(ProcessObservationError, 'fenced'):
            self.sampler.sample()

    def test_counter_and_clock_regressions_fail_closed(self):
        self.sampler.sample()
        self.clock.now = 1
        self.process(101, 10, 1, 0, 1200)
        with self.assertRaisesRegex(ProcessObservationError, 'counter decreased'):
            self.sampler.sample()
        other = LinuxProcSampler({'server': (101, 10)}, proc_root=self.proc,
                                 clock=self.clock, clock_ticks=100)
        other.sample()
        self.clock.now = 0
        with self.assertRaisesRegex(ProcessObservationError, 'timestamps did not advance'):
            other.sample()

    def test_one_second_sampling_schedule(self):
        samples = list(self.sampler.samples(3, sleep=self.clock.sleep))
        self.assertEqual([sample['monotonic_time'] for sample in samples], [0, 1, 2, 3])
        with self.assertRaises(ValueError):
            list(self.sampler.samples(1, interval_seconds=0.5, sleep=self.clock.sleep))


if __name__ == '__main__':
    unittest.main()
