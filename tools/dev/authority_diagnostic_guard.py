"""Optional bounded reuse of expensive checks in isolated native diagnostics.

This is not a production authorization cache. Callers still own process cleanup,
protocol checks and motion bounds. An unchanged cheap check does not establish
unchanged files or remote socket ownership between full observations.
"""
from contextlib import contextmanager
import math
import os
import select
import threading
import time


MAX_CACHE_SECONDS = 0.250


class LinuxDiagnosticProcess:
    """Retain an exact Linux process exit handle and caller-owned local sockets.

    This cheap observation checks exit and local descriptor identity/address.
    It does not establish the process executable, remote socket ownership or
    checkpoint contents; those remain the full callback's responsibility.
    Close this handle after the caller's motion cleanup, before killing X4.
    """

    def __init__(self, *, process, sockets):
        from authority_tcp_native_worker import check_process

        self._pidfd = None
        try:
            check_process(process)
            self._pidfd = os.pidfd_open(process['pid'])
            self._pidfd_identity = self._identity(self._pidfd)
            # Bind the handle between fresh checks of the expected PID lifetime.
            check_process(process)
            self._sockets = tuple((sock, sock.fileno(), self._identity(sock.fileno()),
                                   sock.getsockname()) for sock in sockets)
            self.check()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _identity(descriptor):
        info = os.fstat(descriptor)
        return info.st_dev, info.st_ino

    def check(self):
        if (self._pidfd is None or
                self._identity(self._pidfd) != self._pidfd_identity):
            raise RuntimeError('diagnostic process handle changed or closed')
        exited, _, exceptional = select.select([self._pidfd], [], [self._pidfd], 0)
        if exited or exceptional:
            raise RuntimeError('diagnostic process exited')
        for sock, descriptor, identity, address in self._sockets:
            if (sock.fileno() != descriptor or self._identity(descriptor) != identity or
                    sock.getsockname() != address):
                raise RuntimeError('diagnostic local socket changed')
        return True

    def close(self):
        if self._pidfd is not None:
            descriptor, self._pidfd = self._pidfd, None
            os.close(descriptor)


class DiagnosticEnvironmentGuard:
    """Serialize checks; reuse only successful, unexpired full observations.

    Zero cache age (the default) performs a full check on every call. Opt-in age
    starts BEFORE the full callback, so time spent checking consumes its lease.
    A cached-mode refresh taking the entire lease fails, even in a strict block.
    Immediate checks run on every call and again after a full check. Exceptions,
    false results, clock regression and reentry permanently disable this guard.

    Use ``strict()`` around admission, control/STOP and lifecycle transitions.
    It checks both boundaries, disables reuse inside, and discards the result
    on exit. No background thread runs: after idle time a fresh check must finish
    before the next operation, but changes are not detected while nobody calls.
    """

    def __init__(self, *, full_check, immediate_check, cache_seconds=0,
                 clock=time.monotonic):
        if (not callable(full_check) or not callable(immediate_check) or
                not callable(clock) or type(cache_seconds) not in (int, float) or
                not math.isfinite(cache_seconds) or
                not 0 <= cache_seconds <= MAX_CACHE_SECONDS):
            raise ValueError('bounded diagnostic guard callbacks and cache age required')
        self._full_check = full_check
        self._immediate_check = immediate_check
        self._cache_seconds = float(cache_seconds)
        self._clock = clock
        self._owner = threading.current_thread()
        self._checking = False
        self._failed = False
        self._strict_depth = 0
        self._validated_at = None
        self._last_clock = None
        self._statistics = {'calls': 0, 'full_checks': 0, 'reused_checks': 0}

    @property
    def statistics(self):
        return dict(self._statistics)

    def _require_available(self):
        if (threading.current_thread() is not self._owner or self._checking or
                self._failed):
            self._failed = True
            self._validated_at = None
            raise RuntimeError('diagnostic guard unavailable or reentrant')

    def _now(self):
        now = self._clock()
        if (type(now) not in (int, float) or not math.isfinite(now) or now < 0 or
                (self._last_clock is not None and now < self._last_clock)):
            raise RuntimeError('diagnostic guard clock invalid or regressed')
        self._last_clock = now
        return now

    def _check_immediate(self):
        if self._immediate_check() is not True or self._failed:
            raise RuntimeError('immediate diagnostic check failed')

    def __call__(self, *, force=False):
        if type(force) is not bool:
            raise ValueError('boolean refresh option required')
        self._require_available()
        self._checking = True
        self._statistics['calls'] += 1
        try:
            self._now()
            self._check_immediate()
            now = self._now()
            refresh = (force or self._strict_depth > 0 or self._cache_seconds == 0 or
                       self._validated_at is None or
                       now - self._validated_at >= self._cache_seconds)
            if refresh:
                self._validated_at = None
                self._statistics['full_checks'] += 1
                started = now
                if self._full_check() is not True or self._failed:
                    raise RuntimeError('full diagnostic check failed')
                self._check_immediate()
                finished = self._now()
                if self._cache_seconds and finished - started >= self._cache_seconds:
                    raise TimeoutError('diagnostic refresh exceeded its cache lifetime')
                self._validated_at = started
            else:
                self._statistics['reused_checks'] += 1
            return True
        except BaseException:
            self._failed = True
            self._validated_at = None
            raise
        finally:
            self._checking = False

    def invalidate(self):
        """Drop reuse before a known context change; the next call is fresh."""
        self._require_available()
        self._validated_at = None

    @contextmanager
    def strict(self):
        """Keep every existing guard call fresh throughout a lifecycle step."""
        self._require_available()
        self._strict_depth += 1
        try:
            self(force=True)
            yield
            self(force=True)
        except BaseException:
            self._failed = True
            raise
        finally:
            self._validated_at = None
            self._strict_depth -= 1
