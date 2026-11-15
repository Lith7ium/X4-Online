"""Linux-only exec-gated single helper lifecycle experiment; no X4 launch.

The helper is trusted not to fork or create descendants. Its owner must reap
it before releasing any X4 process lock; a failed stop is not successful
cleanup. Sensitive configuration belongs in inherited private FDs, not argv.
SIGCHLD must remain default, and no other handler, thread or library may reap
this child; otherwise initial PID-to-pidfd binding cannot be guaranteed.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

GATE = Path(__file__).resolve().with_name('authority_exec_gate.py')
_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


class HelperCleanupError(RuntimeError):
    """Failed startup cleanup; helper remains accessible for fencing/reap."""
    def __init__(self, helper):
        super().__init__('helper stop unconfirmed; retain X4 lock and retry cleanup')
        self.helper = helper


class OwnedHelper:
    """One unreleased exec gate and a pidfd-pinned child; no child tree."""
    def __init__(self, command, *, registry, pass_fds=()):
        if (sys.platform != 'linux' or threading.current_thread() is not threading.main_thread() or
                not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal') or
                not hasattr(os, 'P_PIDFD') or signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL or
                not isinstance(command, (list, tuple)) or not command or
                any(type(x) is not str or not x for x in command) or
                type(registry) is not list or
                not isinstance(pass_fds, (list, tuple)) or
                any(type(fd) is not int or fd < 0 for fd in pass_fds)):
            raise ValueError('main-thread Linux pidfd and valid helper configuration required')
        self.proc = None; self.pidfd = self.gate = None; self.released = False
        # Register before Popen so the owner can clean up even if an
        # interruption arrives before this constructor returns.
        registry.append(self)
        read_fd = write_fd = None
        previous = {}; pending = [None]
        def remember(number, frame): pending[0] = pending[0] or number
        try:
            for number in _SIGNALS: previous[number] = signal.signal(number, remember)
            read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
            self.proc = subprocess.Popen([sys.executable, str(GATE), str(read_fd), *command],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True, pass_fds=tuple(set((read_fd, *pass_fds))))
            os.close(read_fd); read_fd = None
            self.gate, write_fd = write_fd, None
            self.pidfd = os.pidfd_open(self.proc.pid)
            if self.proc.poll() is not None: raise RuntimeError('helper exited before gate release')
            if pending[0] is not None: raise InterruptedError('signal '+str(pending[0]))
        except BaseException as error:
            # A Popen child cannot have its PID recycled while unreaped. It
            # cannot execute the target before the private gate is released.
            if self.gate is not None:
                os.close(self.gate); self.gate = None
            if self.proc is not None:
                try:
                    if self.proc.poll() is None: self.proc.kill()
                    self.proc.wait(timeout=3)
                except BaseException:
                    raise HelperCleanupError(self) from error
                if self.pidfd is not None: os.close(self.pidfd); self.pidfd = None
            raise
        finally:
            for fd in (read_fd, write_fd):
                if fd is not None: os.close(fd)
            for number, handler in previous.items(): signal.signal(number, handler)
        if pending[0] is not None:
            self.stop()
            raise InterruptedError('signal '+str(pending[0]))

    def release(self):
        if self.gate is None or self.released or self.proc.poll() is not None:
            raise RuntimeError('helper gate unavailable')
        try:
            # Once the write begins an interruption may hide whether the
            # target ran; cleanup must treat it as possibly released.
            self.released = True
            if os.write(self.gate, b'G') != 1: raise RuntimeError('helper gate refused')
        finally:
            os.close(self.gate); self.gate = None

    def stop(self, *, grace=.25, kill_wait=2):
        """Reap exact child, escalating to SIGKILL; retain pidfd on failure."""
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('helper cleanup requires main thread')
        if not 0 <= grace <= 5 or not 0 < kill_wait <= 10:
            raise ValueError('invalid helper cleanup timeout')
        previous = {}
        try:
            for number in _SIGNALS: previous[number] = signal.signal(number, signal.SIG_IGN)
            if (self.proc is not None and self.proc.returncode is None and
                    signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL):
                raise RuntimeError('SIGCHLD changed; helper cleanup unconfirmed')
            if self.gate is not None: os.close(self.gate); self.gate = None
            if self.proc is None: return None
            if self.proc.returncode is not None:
                # This Popen has already recorded the owner's wait/poll.
                if self.pidfd is not None: os.close(self.pidfd); self.pidfd = None
                return self.proc.returncode
            if self.pidfd is not None:
                try:
                    os.waitid(os.P_PIDFD, self.pidfd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                except ChildProcessError as error:
                    raise RuntimeError('helper reaped externally; cleanup unconfirmed') from error
            if self.proc.poll() is None:
                try:
                    if self.pidfd is not None: signal.pidfd_send_signal(self.pidfd, signal.SIGTERM)
                    else: self.proc.terminate()  # unreaped Popen PID cannot be reused
                except ProcessLookupError: pass
                try: self.proc.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    try:
                        if self.pidfd is not None: signal.pidfd_send_signal(self.pidfd, signal.SIGKILL)
                        else: self.proc.kill()
                    except ProcessLookupError: pass
                    self.proc.wait(timeout=kill_wait)
            else:
                self.proc.wait(timeout=kill_wait)
            status = self.proc.returncode
            if self.pidfd is not None: os.close(self.pidfd); self.pidfd = None
            return status
        finally:
            for number, handler in previous.items(): signal.signal(number, handler)
