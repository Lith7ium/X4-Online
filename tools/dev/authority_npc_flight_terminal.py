"""One-shot isolated test fence; never starts X4 and never admits clients.

The caller owns the process cleanup. Any exception poisons this controller and
must cause both disposable X4 processes to be terminated. After begin(), the
coordinator is deliberately stale and must never be used again.
"""
import time


class TerminalControl:
    def __init__(self, *, world, engine, offers, service, check_processes, deadline, bridge_timeout):
        if not callable(check_processes) or bridge_timeout <= 0:
            raise ValueError('explicit process check and timeout required')
        self._world=world;self._engine=engine;self._offers=offers;self._service=service
        self._check=check_processes;self._deadline=deadline;self._timeout=bridge_timeout
        self.state='new'

    def _time_and_processes(self):
        # No operation can outlive the enclosing deadline. Refuse rather than
        # changing the bridge's internally configured timeout mid-request.
        if self._deadline-time.monotonic() <= self._timeout+1:
            raise TimeoutError('insufficient deadline for bounded bridge operation')
        if self._check() is not True: raise RuntimeError('owned process/Steam identity changed')

    def begin(self):
        if self.state!='new': raise RuntimeError('terminal fence is one-shot')
        self.state='failed'
        self._time_and_processes()
        session=self._world.session
        if session.state!='paused' or session.pending is not None or session.ready_players:
            raise RuntimeError('coordinator not quiescent')
        self._offers.invalidate()
        self._service.close()
        self._time_and_processes()
        # Remove access inside this controller as well; the runner must not use
        # any other reference to the coordinator once the fence is entered.
        self._world=None;self._offers=None;self._service=None
        self.state='fenced'

    def resume(self):
        if self.state!='fenced': raise RuntimeError('terminal resume not permitted')
        self.state='failed';self._time_and_processes()
        self._engine.resume()
        self._time_and_processes()
        self.state='running'

    def source_stopped(self):
        if self.state!='running': raise RuntimeError('source stop out of order')
        self.state='failed'
        self._time_and_processes()
        self.state='source_stopped'

    def pause(self):
        if self.state!='source_stopped': raise RuntimeError('stop source before pausing')
        self.state='failed';self._time_and_processes()
        self._engine.pause()
        self._time_and_processes()
        self.state='paused'
