"""Bounded, in-process live-source input for the private native playback trial.

Producer receipt times use Python time.monotonic(); source_time remains source
X4 game time. This queue establishes neither native velocity nor clock equality.

Inject an instance as the existing playback_driver argument. Wait for wait_ready
before producing; accept_motion is the participant callback, submit allows an
explicit receipt timestamp, and finish is an explicit diagnostic EOF. Failure or
illegal post-EOF input stays visible until native-fenced cleanup closes input.
There is no producer thread or automatic network EOF here.

Receipt age bounds only the queue and time BEFORE UDP dispatch. The native IPC
retains its own deadline and Lua records its own UDP arrival, not this receipt.
The .25-second default is a diagnostic limit, not a network drop policy.
"""
import copy
from collections import deque
import math
import threading
import time

from authority.experimental_tcp_motion import motion_value


class LiveSourceInput:
    def __init__(self, *, epoch, index, sector_macro, capacity=2, max_samples=64,
                 max_seconds=10, receipt_max_age=.25):
        if (type(capacity) is not int or not 1 <= capacity <= 16 or
                type(max_samples) is not int or not 2 <= max_samples <= 64 or
                any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
                    for value in (max_seconds, receipt_max_age)) or
                max_seconds > 10 or receipt_max_age > 5):
            raise ValueError('stream_invalid_limits')
        # Reuse the existing portable schema to validate the fixed identity.
        motion_value(dict(version=1, epoch=epoch, generation='0'*32, index=index,
                          sequence=1, sector_macro=sector_macro, source_time=0,
                          x=0, y=0, z=0, velocity=None))
        self._identity = (epoch, index, sector_macro)
        self.capacity, self.max_samples = capacity, max_samples
        self.max_seconds, self.receipt_max_age = max_seconds, receipt_max_age
        self._condition = threading.Condition()
        self._queue = deque()
        self._initial = self._started = self._previous = self._failure = None
        self._finished = self._closed = False
        self._accepted = 0

    @property
    def identity(self):
        return self._identity

    def check(self):
        with self._condition:
            self._check()

    def failure_code(self):
        with self._condition:
            return self._failure

    def _reject(self, code):
        self._failure = self._failure or code
        self._queue.clear()
        self._condition.notify_all()
        raise ValueError(self._failure)

    def _check(self):
        if self._failure:
            raise ValueError(self._failure)
        if self._closed:
            raise ValueError('stream_closed')

    def wait_ready(self, timeout):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('stream_invalid_wait')
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._initial is None:
                self._check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('stream_readiness_timeout')
                self._condition.wait(min(.05, remaining))
            self._check()
            return copy.deepcopy(self._initial)

    def submit(self, sample, *, received_at):
        with self._condition:
            self._check()
            if self._initial is None or self._finished:
                self._reject('stream_not_accepting')
            now = time.monotonic()
            if (type(received_at) not in (int, float) or not math.isfinite(received_at) or
                    received_at > now or now - received_at > self.receipt_max_age):
                self._reject('stream_invalid_receipt')
            try:
                value = motion_value(sample)
            except (ValueError, TypeError, OverflowError):
                self._reject('stream_invalid_sample')
            if value['version'] != 1 or (value['epoch'], value['index'], value['sector_macro']) != self.identity:
                self._reject('stream_foreign_identity')
            if self._previous:
                previous, previous_receipt = self._previous
                if (value['generation'] != previous['generation'] or value['sequence'] <= previous['sequence'] or
                        value['source_time'] <= previous['source_time'] or received_at < previous_receipt):
                    self._reject('stream_regressed_sample')
            if self._accepted >= self.max_samples or now - self._started >= self.max_seconds:
                self._reject('stream_limit_exceeded')
            if len(self._queue) >= self.capacity:
                self._reject('stream_overflow')
            self._queue.append((value, received_at))
            self._previous = (value, received_at)
            self._accepted += 1
            self._condition.notify_all()

    def accept_motion(self, sample, despawn):
        """Participant callback: True confirms queue acceptance, never movement."""
        if despawn is not False:
            with self._condition:
                self._reject('stream_despawn_unsupported')
        self.submit(sample, received_at=time.monotonic())
        return True

    def validate_dispatch(self, received_at):
        with self._condition:
            self._check()
            now = time.monotonic()
            if received_at > now or now - received_at > self.receipt_max_age:
                self._reject('stream_invalid_receipt')
            if now - self._started >= self.max_seconds:
                self._reject('stream_limit_exceeded')
            return now

    def finish(self):
        with self._condition:
            self._check()
            if self._initial is None or self._finished or self._accepted < 2:
                self._reject('stream_invalid_eof')
            self._finished = True
            self._condition.notify_all()

    def fail(self):
        with self._condition:
            if self._closed:
                return
            try:
                self._reject('stream_producer_failed')
            except ValueError:
                pass

    def _ready(self, initial):
        with self._condition:
            self._check()
            if self._initial is not None:
                self._reject('stream_already_started')
            self._initial = copy.deepcopy(initial)
            self._started = time.monotonic()
            self._condition.notify_all()

    def _next(self, *, guard, abort, deadline):
        while True:
            guard()
            if abort.is_set() or time.monotonic() >= deadline:
                raise RuntimeError('stream_consumer_fenced')
            with self._condition:
                self._check()
                if self._initial is None:
                    self._reject('stream_not_ready')
                now = time.monotonic()
                if now - self._started >= self.max_seconds:
                    self._reject('stream_limit_exceeded')
                if self._queue:
                    value, received_at = self._queue.popleft()
                    if received_at > now or now - received_at > self.receipt_max_age:
                        self._reject('stream_invalid_receipt')
                    return copy.deepcopy(value), received_at
                if self._finished:
                    return None
                self._condition.wait(min(.05, deadline-now, self.max_seconds-(now-self._started)))

    def _close(self):
        with self._condition:
            self._closed = True
            self._queue.clear()
            self._condition.notify_all()
