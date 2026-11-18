"""One bounded metadata-check phase for an owned two-X4 playback diagnostic.

The caller serializes all writers and its FD table and keeps both private saves
read-only in X4. Metadata checks are not proof of unchanged bytes or a writer
lock. Full checks bracket this phase; no thread, socket reader or helper is
owned here. The process guard must return True without entering this window or
an aggregate save guard. The separately owned checkpoint-helper pump may
check local save pins during this window's explicitly owned helper requests.
"""
import math
import time
import threading

from authority_fixture_save_guards import FixtureSaveGuards
from authority_witness_source_guard import WitnessSourceGuard
from authority_witness_guard_client import WitnessGuardClient


class PlaybackSamplingWindow:
    def __init__(self, full_sha, source_guard):
        if not isinstance(source_guard, WitnessSourceGuard):
            raise ValueError('verified witness source guard required')
        self._source = source_guard
        self._original_source = source_guard
        self._saves = FixtureSaveGuards(full_sha)
        self.state = 'unopened'
        self.failed = False
        self._busy = False
        self._owner = threading.get_ident()
        self._checkpoint = self._helper = self._process = None
        self._process_guard = None
        self._deadline = None
        self._pidfd = None
        self._helper_io = None
        self._local_save_busy = False
        self.metrics = dict(source_full_checks=0, source_metadata_checks=0,
                            checkpoint_full_checks=0, checkpoint_metadata_checks=0,
                            windows=0, saves=self._saves.metrics,
                            exclusive_writer_and_fd_owner_assumed=True,
                            unchanged_bytes_between_boundaries_proven=False)

    @property
    def active(self):
        return self.state == 'active' and not self.failed

    def _begin(self):
        if (self.failed or self._busy or threading.get_ident() != self._owner or
                self._source is not self._original_source):
            self.failed = True
            raise RuntimeError('playback sampling window failed or reentered')
        self._busy = True

    def _context(self, *, stopped=False):
        if self.failed or self._source is not self._original_source:
            raise RuntimeError('playback sampling context changed')
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise TimeoutError('playback sampling deadline expired')
        guard = self._checkpoint
        if guard is not None:
            if guard.helper is not self._helper or guard.helper.proc is not self._process:
                raise RuntimeError('playback checkpoint helper changed')
            if stopped or guard.state == 'stopped':
                if guard.state != 'stopped' or self._process.poll() != 0 or self._helper.pidfd is not None:
                    raise RuntimeError('full checkpoint STOP not confirmed')
            else:
                local_helper_check = self._helper_io is guard and self._local_save_busy
                permitted_states = ('ready', 'checking', 'stopping') if local_helper_check else ('ready',)
                exits = (None, 0) if local_helper_check and guard.state == 'stopping' else (None,)
                if (guard.state not in permitted_states or self._process.poll() not in exits or
                        self._helper.pidfd != self._pidfd):
                    raise RuntimeError('playback checkpoint helper unavailable')

    def _process_check(self, *, stopped=False):
        self._context(stopped=stopped)
        if self._process_guard() is not True:
            raise RuntimeError('playback process guard did not confirm')
        self._context(stopped=stopped)
        return True

    def _run(self, operation):
        self._begin()
        try:
            result = operation()
            if result is not True or self.failed:
                raise RuntimeError('playback sampling check did not confirm')
            return True
        except BaseException:
            self.failed = True
            raise
        finally:
            self._busy = False

    def _helper_request(self, guard, operation):
        if self._helper_io is not None or not isinstance(guard, WitnessGuardClient):
            raise RuntimeError('playback helper request reentered or invalid')
        self._helper_io = guard
        try:
            return operation()
        finally:
            self._helper_io = None

    def _nested_save_check(self, path, digest):
        # Only the owned helper's pump may enter this local, non-IPC operation.
        # Never release the outer busy flag or permit a second nested check.
        if (self.failed or threading.get_ident() != self._owner or self._local_save_busy or
                self._source is not self._original_source):
            self.failed = True
            raise RuntimeError('playback nested save check unavailable')
        self._local_save_busy = True
        try:
            if self._checkpoint is not None: self._process_check()
            result = self._saves.check(path, digest)
            if self._checkpoint is not None: self._process_check()
            if result is not True or self.failed:
                raise RuntimeError('playback nested save check did not confirm')
            return True
        except BaseException:
            self.failed = True
            raise
        finally:
            self._local_save_busy = False

    def check_save(self, path, digest):
        if self._busy and self._helper_io is not None:
            return self._nested_save_check(path, digest)
        def check():
            if self.state == 'active': self._process_check()
            result = self._saves.check(path, digest)
            if self.state == 'active': self._process_check()
            return result
        return self._run(check)

    def check_source(self):
        def check():
            if self.state == 'active':
                self._process_check()
                self.metrics['source_metadata_checks'] += 1
                result = self._source.check_metadata()
                self._process_check()
            else:
                self.metrics['source_full_checks'] += 1
                result = self._source.check()
            return result
        return self._run(check)

    def check_checkpoint(self, guard):
        def check():
            if self.state == 'active':
                if guard is not self._checkpoint:
                    raise RuntimeError('playback checkpoint guard changed')
                self._process_check()
                self.metrics['checkpoint_metadata_checks'] += 1
                result = self._helper_request(guard, guard.check_metadata)
                self._process_check()
            else:
                self.metrics['checkpoint_full_checks'] += 1
                result = self._helper_request(guard, guard.check)
            return result
        return self._run(check)

    def open(self, entries, checkpoint_guard, *, process_guard, deadline):
        def enter():
            if (self.state != 'unopened' or not isinstance(checkpoint_guard, WitnessGuardClient) or
                    not callable(process_guard) or
                    type(deadline) not in (int, float) or not math.isfinite(deadline) or
                    not time.monotonic() < deadline <= time.monotonic() + 60):
                raise ValueError('one bounded playback sampling phase required')
            self._checkpoint = checkpoint_guard
            self._helper = checkpoint_guard.helper
            self._process = self._helper.proc
            self._pidfd = self._helper.pidfd
            self._process_guard = process_guard
            self._deadline = float(deadline)
            self._process_check()
            self.metrics['source_full_checks'] += 1
            if self._source.check() is not True:
                raise RuntimeError('source full boundary failed')
            self._process_check()
            self._saves.open(entries, expected_count=2)
            self._saves.boundary(self._process_check)
            self._process_check()
            self.metrics['checkpoint_full_checks'] += 1
            if self._helper_request(checkpoint_guard, checkpoint_guard.check) is not True:
                raise RuntimeError('checkpoint full boundary failed')
            self._process_check()
            self.state = 'active'
            self.metrics['windows'] += 1
            return True
        return self._run(enter)

    def stop_checkpoint(self, guard):
        """Run the existing full STOP with local save checks allowed in its pump."""
        def stop():
            if self.state != 'active' or guard is not self._checkpoint:
                raise RuntimeError('playback checkpoint guard changed or inactive')
            self._process_check()
            result = self._helper_request(guard, guard.stop)
            self._process_check(stopped=True)
            return result
        return self._run(stop)

    def close(self, *, process_guard):
        """Full exit boundary; use the same pure process callback as open()."""
        def leave():
            if self.state != 'active' or process_guard is not self._process_guard:
                raise RuntimeError('playback sampling window cannot close')
            # WitnessGuardClient.stop() performs its full check before STOPPED.
            # No request is sent to its now stopped helper from this boundary.
            stopped_check = lambda: self._process_check(stopped=True)
            stopped_check()
            self._saves.boundary(stopped_check)
            stopped_check()
            self.metrics['source_full_checks'] += 1
            if self._source.check() is not True:
                raise RuntimeError('source full boundary failed')
            stopped_check()
            self._saves.close()
            stopped_check()
            self.state = 'closed'
            self._deadline = None
            return True
        return self._run(leave)

    def cleanup(self):
        """Release save FDs without declaring a failed/abandoned phase valid."""
        if self._busy or threading.get_ident() != self._owner:
            self.failed = True
            raise RuntimeError('playback sampling cleanup reentered or wrong thread')
        if self.state == 'active': self.failed = True
        try:
            self._saves.close()
        except BaseException:
            self.failed = True
            raise
        if self.state == 'unopened': self.state = 'closed'
        return True
