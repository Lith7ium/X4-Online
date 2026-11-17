"""Owner-loop and game-clock measurement contract without an X4 process."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from authority.linux_proc_measurement import measure_running_window


class Clock:
    def __init__(self): self.value = 0.0
    def __call__(self): return self.value
    def tick(self): self.value += 0.25


class Sampler:
    def __init__(self, clock): self.clock, self.times = clock, []
    def sample(self):
        self.times.append(self.clock())
        return {'monotonic_time': self.clock()}


class MeasurementTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.sampler = Sampler(self.clock)
        self.args = dict(enabled=True, sampler=self.sampler, read_running_game_time=self.clock,
                         tick=self.clock.tick, check=lambda: None, duration_seconds=3,
                         deadline=10, monotonic=self.clock)

    def test_owner_is_pumped_and_real_intervals_recorded(self):
        result = measure_running_window(**self.args)
        self.assertEqual(self.sampler.times, [0, 1, 2, 3])
        self.assertEqual((result['game_time_before'], result['game_time_after']), (0, 3))
        self.assertFalse(result['frame_times_measured'])

    def test_slow_tick_does_not_invent_missing_samples(self):
        def slow_tick(): self.clock.value += 2.5
        self.args.update(tick=slow_tick, duration_seconds=4)
        result = measure_running_window(**self.args)
        self.assertEqual(self.sampler.times, [0, 2.5, 5])
        self.assertEqual(result['elapsed_seconds'], 5)

    def test_nonintegral_duration_takes_an_explicit_final_sample(self):
        self.args['duration_seconds'] = 3.5
        result = measure_running_window(**self.args)
        self.assertEqual(self.sampler.times, [0, 1, 2, 3, 3.5])
        self.assertEqual(result['elapsed_seconds'], 3.5)

    def test_fast_ticks_are_rate_limited_without_skipping_owner_checks(self):
        ticks, checks, waits = [], [], []
        def tick(): ticks.append(self.clock())
        def check(): checks.append(self.clock())
        def sleep(duration):
            waits.append(duration)
            self.clock.value += duration
        self.args.update(tick=tick, check=check, sleep=sleep, duration_seconds=1)
        result = measure_running_window(**self.args)
        self.assertGreater(len(waits), 0)
        self.assertLessEqual(len(ticks), 102)
        self.assertGreater(len(checks), 2 * len(ticks))
        self.assertGreaterEqual(result['elapsed_seconds'], 1)

    def test_duration_shorter_than_interval_still_finishes_on_time(self):
        self.args.update(duration_seconds=2, interval_seconds=60)
        result = measure_running_window(**self.args)
        self.assertEqual(self.sampler.times, [0, 2])
        self.assertEqual(result['elapsed_seconds'], 2)

    def test_no_game_time_progress_or_paused_receipt_fails(self):
        self.args['read_running_game_time'] = lambda: 10
        with self.assertRaisesRegex(ValueError, 'did not advance'):
            measure_running_window(**self.args)
        self.clock.value = 0
        def paused(): raise RuntimeError('game is paused')
        self.args['read_running_game_time'] = paused
        with self.assertRaisesRegex(RuntimeError, 'paused'):
            measure_running_window(**self.args)

    def test_context_loss_and_deadline_fail_without_result(self):
        self.args['check'] = lambda: self.clock() < 1
        with self.assertRaisesRegex(RuntimeError, 'owner context changed'):
            measure_running_window(**self.args)
        self.clock.value = 0
        self.args.update(check=lambda: None, deadline=3.1)
        def slow_tick(): self.clock.value += 2
        self.args['tick'] = slow_tick
        with self.assertRaises(TimeoutError):
            measure_running_window(**self.args)

    def test_sampler_failure_and_non_opt_in_fail(self):
        self.args['enabled'] = False
        with self.assertRaises(ValueError): measure_running_window(**self.args)
        self.args['enabled'] = True
        def failed_sample(): raise RuntimeError('process disappeared')
        self.sampler.sample = failed_sample
        with self.assertRaisesRegex(RuntimeError, 'disappeared'):
            measure_running_window(**self.args)


if __name__ == '__main__': unittest.main()
