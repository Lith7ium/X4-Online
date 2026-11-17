"""Lightweight Linux process measurements for explicitly owned PIDs.

CPU percentages use one logical CPU as 100%. RSS includes shared resident
pages, so summing RSS does not measure unique physical memory. The sampler
never estimates rendering frame times. A PID/start-time mismatch or loss of an
observed process invalidates the observation; short-lived threads may be missed
between samples and are reported without invented CPU rates when detected.
"""
from pathlib import Path
import math
import os
import time


class ProcessObservationError(RuntimeError):
    """A pinned process disappeared, changed identity, or could not be read."""


def _read_stat(path):
    text = path.read_text(encoding='utf-8')
    opening = text.find('(')
    closing = text.rfind(')')
    if opening <= 0 or closing <= opening:
        raise ValueError('invalid process stat')
    fields = text[closing + 1:].split()
    if len(fields) < 20:
        raise ValueError('incomplete process stat')
    pid = int(text[:opening].strip())
    user_ticks, system_ticks, start_ticks = (int(fields[i]) for i in (11, 12, 19))
    if pid <= 0 or min(user_ticks, system_ticks, start_ticks) < 0:
        raise ValueError('invalid process stat counters')
    return {'pid': pid, 'name': text[opening + 1:closing],
            'cpu_ticks': user_ticks + system_ticks, 'start_ticks': start_ticks}


def _read_rss_bytes(path):
    matches = [line.split() for line in path.read_text(encoding='utf-8').splitlines()
               if line.startswith('VmRSS:')]
    if len(matches) != 1 or len(matches[0]) != 3 or matches[0][2] != 'kB':
        raise ValueError('missing or invalid VmRSS')
    value = int(matches[0][1])
    if value < 0:
        raise ValueError('invalid VmRSS')
    return value * 1024


class LinuxProcSampler:
    """Measure named processes supplied as ``{name: (pid, start_ticks)}``.

    The first sample establishes a baseline; subsequent samples report CPU
    percentages since the previous sample. Only a thread present with the same
    TID and start time at both ends has a computable rate. Measurements are
    observational and do not keep processes alive or freeze their threads.
    """

    def __init__(self, processes, *, proc_root='/proc', clock=time.monotonic,
                 clock_ticks=None):
        if not isinstance(processes, dict) or not processes or not callable(clock):
            raise ValueError('named pinned processes and monotonic clock required')
        self.processes = {}
        seen = set()
        for name, identity in processes.items():
            if (type(name) is not str or not name or type(identity) is not tuple or
                    len(identity) != 2 or any(type(value) is not int for value in identity) or
                    identity[0] <= 0 or identity[1] < 0 or identity[0] in seen):
                raise ValueError('invalid or duplicate process identity')
            self.processes[name] = identity
            seen.add(identity[0])
        self.proc_root = Path(proc_root)
        self.clock = clock
        self.clock_ticks = os.sysconf('SC_CLK_TCK') if clock_ticks is None else clock_ticks
        if type(self.clock_ticks) is not int or self.clock_ticks <= 0:
            raise ValueError('invalid CPU clock tick rate')
        self._previous = None
        self._failed = False

    def _read_process(self, pid, expected_start):
        directory = self.proc_root / str(pid)
        try:
            first = _read_stat(directory / 'stat')
            if first['pid'] != pid or first['start_ticks'] != expected_start:
                raise ProcessObservationError('process identity changed')
            rss_bytes = _read_rss_bytes(directory / 'status')
            threads = {}
            unreadable = []
            for entry in sorted((directory / 'task').iterdir(), key=lambda item: item.name):
                if not entry.name.isascii() or not entry.name.isdecimal():
                    continue
                tid = int(entry.name)
                try:
                    thread = _read_stat(entry / 'stat')
                except FileNotFoundError:
                    unreadable.append(tid)
                    continue
                if thread['pid'] != tid:
                    raise ProcessObservationError('thread identity changed while reading')
                threads[tid] = thread
            last = _read_stat(directory / 'stat')
            if last['pid'] != pid or last['start_ticks'] != expected_start:
                raise ProcessObservationError('process identity changed during sample')
            if last['cpu_ticks'] < first['cpu_ticks']:
                raise ProcessObservationError('process CPU counter decreased')
            return {'pid': pid, 'start_ticks': expected_start, 'cpu_ticks': last['cpu_ticks'],
                    'rss_bytes': rss_bytes, 'threads': threads, 'unreadable_threads': unreadable}
        except (OSError, ValueError) as error:
            raise ProcessObservationError(f'cannot sample process {pid}: {error}') from error

    def sample(self):
        if self._failed:
            raise ProcessObservationError('sampler fenced after failed observation')
        try:
            started = self.clock()
            current = {name: self._read_process(*identity) for name, identity in self.processes.items()}
            finished = self.clock()
            if not all(math.isfinite(value) for value in (started, finished)) or finished < started:
                raise ProcessObservationError('monotonic clock moved backwards')
            timestamp = (started + finished) / 2
            elapsed = None if self._previous is None else timestamp - self._previous['timestamp']
            if elapsed is not None and elapsed <= 0:
                raise ProcessObservationError('sample timestamps did not advance')
            result = {'monotonic_time': timestamp, 'collection_seconds': finished - started,
                      'interval_seconds': elapsed, 'processes': {}}
            for name, process in current.items():
                previous = None if self._previous is None else self._previous['processes'][name]
                rate = None
                if previous is not None:
                    delta = process['cpu_ticks'] - previous['cpu_ticks']
                    if delta < 0:
                        raise ProcessObservationError('process CPU counter decreased between samples')
                    rate = 100 * delta / self.clock_ticks / elapsed
                old_threads = {} if previous is None else previous['threads']
                thread_results = []
                for tid, thread in sorted(process['threads'].items()):
                    old = old_threads.get(tid)
                    thread_rate = None
                    if old is not None and old['start_ticks'] == thread['start_ticks']:
                        delta = thread['cpu_ticks'] - old['cpu_ticks']
                        if delta < 0:
                            raise ProcessObservationError('thread CPU counter decreased')
                        thread_rate = 100 * delta / self.clock_ticks / elapsed
                    thread_results.append({'tid': tid, 'start_ticks': thread['start_ticks'],
                                           'name': thread['name'], 'cpu_percent': thread_rate})
                gone = [{'tid': tid, 'start_ticks': thread['start_ticks']}
                        for tid, thread in sorted(old_threads.items())
                        if tid not in process['threads'] or
                        process['threads'][tid]['start_ticks'] != thread['start_ticks']]
                result['processes'][name] = {'pid': process['pid'], 'start_ticks': process['start_ticks'],
                    'rss_bytes': process['rss_bytes'], 'cpu_percent': rate, 'threads': thread_results,
                    'threads_no_longer_observed': gone, 'threads_unreadable': process['unreadable_threads']}
            self._previous = {'timestamp': timestamp, 'processes': current}
            return result
        except Exception:
            self._failed = True
            raise

    def samples(self, duration_seconds, *, interval_seconds=1.0, sleep=time.sleep):
        """Yield a baseline then samples at intervals of at least one second.

        The caller owns this generator and its lifetime; slow collection delays
        later samples instead of causing a burst of catch-up reads.
        """
        if (type(duration_seconds) not in (int, float) or not math.isfinite(duration_seconds) or
                duration_seconds <= 0 or type(interval_seconds) not in (int, float) or
                not math.isfinite(interval_seconds) or interval_seconds < 1 or not callable(sleep)):
            raise ValueError('invalid sampling duration or interval')
        start = self.clock()
        deadline = start + duration_seconds
        yield self.sample()
        next_sample = self.clock() + interval_seconds
        while next_sample <= deadline:
            while True:
                remaining = next_sample - self.clock()
                if remaining <= 0:
                    break
                sleep(remaining)
            if self.clock() > deadline:
                break
            yield self.sample()
            next_sample = self.clock() + interval_seconds
