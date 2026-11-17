"""Experimental handle-bound Windows child lifecycle; never launch X4 with it.

The owner starts exactly one direct child and retains its CPython Popen object
and Windows process handle. There is no PID lookup, descendant management,
profile access, log authentication, executable-image verification or durable
recovery. In particular, an interruption inside Popen may leave a started
process without an obtainable handle. Such a start remains indeterminate and
must never be called cleaned up or used to release/reuse a profile. The X4
startup window is not yet controlled or proven; this adapter must not be wired
to X4 until it is. Caller exclusively owns the adapter and all its handles.
"""
from contextlib import contextmanager
import math
import os
from pathlib import Path
import subprocess
import threading


def _windows_runtime():
    return os.name == 'nt'


def _timeout(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 300:
        raise ValueError('timeout must be between 0 and 300 seconds')
    return float(value)


class ExperimentalWindowsOwnedProcess:
    """One direct Windows child; operations are confined to its owner thread.

    A Popen failure is permanently indeterminate, even if no child appears to
    exist. Cleanup is confirmed only after a known owned handle reports exit.
    An uncertain stop is never repeated; callers may still wait for that same
    handle to report exit. No claim about a child process tree is made.
    """

    def __init__(self, *, enabled=False):
        if enabled is not True or not _windows_runtime():
            raise ValueError('explicit Windows experiment opt-in required')
        self._owner = threading.current_thread()
        self._busy = False
        self._phase = 'new'
        self._process = None
        self._handle = None
        self._pid = None
        self._returncode = None
        self._stop_dispatched = False

    @contextmanager
    def _operation(self):
        if threading.current_thread() is not self._owner:
            raise RuntimeError('exclusive process owner thread required')
        if self._busy:
            raise RuntimeError('reentrant process owner operation')
        self._busy = True
        try:
            yield
        finally:
            self._busy = False

    def _known_process(self):
        process = self._process
        if (process is None or self._handle is None or
                getattr(process, '_handle', None) is not self._handle or
                process.pid != self._pid):
            self._phase = 'unknown'
            raise RuntimeError('owned process handle unavailable or changed')
        return process

    def _record_exit(self, returncode):
        if type(returncode) is not int:
            self._phase = 'unknown'
            raise RuntimeError('invalid process exit result')
        self._returncode = returncode
        self._phase = 'exited'
        return returncode

    def start(self, command, *, cwd, env):
        """Start once. A raised Popen call leaves an unresolved start state.

        The X4.exe basename is refused as an additional guard, not as a
        complete executable-identity check (aliases can have other names).
        """
        with self._operation():
            if self._phase != 'new':
                raise RuntimeError('process start already attempted')
            if (type(command) not in (list, tuple) or not command or
                    any(type(arg) is not str or not arg or '\0' in arg for arg in command) or
                    not Path(command[0]).is_absolute() or
                    type(cwd) is not str or not Path(cwd).is_absolute() or not Path(cwd).is_dir() or
                    type(env) is not dict or any(type(key) is not str or type(value) is not str or
                        not key or '\0' in key or '\0' in value for key, value in env.items())):
                raise ValueError('absolute command, existing cwd and explicit environment required')
            if Path(command[0]).name.casefold() == 'x4.exe':
                raise ValueError('X4 startup is not supported by this experiment')
            # A process may exist even if Popen is interrupted before returning.
            # No caller may infer cleanup or retry from a failure at this point.
            self._phase = 'start_unknown'
            process = subprocess.Popen(list(command), cwd=cwd, env=dict(env), shell=False,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, close_fds=True)
            self._process = process
            self._handle = getattr(process, '_handle', None)
            self._pid = process.pid
            if self._handle is None or type(self._pid) is not int or self._pid < 1:
                self._phase = 'unknown'
                raise RuntimeError('created process handle unavailable')
            self._phase = 'running'

    def poll(self):
        """Return None while running, or the owned child's observed exit code."""
        with self._operation():
            if self._phase == 'exited':
                return self._returncode
            process = self._known_process()
            try:
                result = process.poll()
            except BaseException:
                self._phase = 'unknown'
                raise
            return None if result is None else self._record_exit(result)

    def wait(self, timeout):
        """Wait on the same handle; timeout leaves exit unconfirmed."""
        timeout = _timeout(timeout)
        with self._operation():
            if self._phase == 'exited':
                return self._returncode
            process = self._known_process()
            try:
                result = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                return None
            except BaseException:
                self._phase = 'unknown'
                raise
            return self._record_exit(result)

    def terminate(self):
        """Dispatch termination at most once to the retained process handle."""
        with self._operation():
            if self._phase == 'exited':
                return
            if self._phase != 'running' or self._stop_dispatched:
                raise RuntimeError('process termination unavailable or already attempted')
            process = self._known_process()
            self._stop_dispatched = True
            self._phase = 'stopping'
            try:
                process.terminate()
            except BaseException:
                self._phase = 'unknown'
                raise

    @property
    def cleanup_confirmed(self):
        """Only the known child's observed exit, not profile/tree cleanup."""
        if threading.current_thread() is not self._owner or self._busy:
            raise RuntimeError('exclusive process owner thread required')
        return self._phase == 'exited'
