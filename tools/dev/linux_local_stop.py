"""Private local-game stop pipes; no relay traffic or process-name signalling."""
import fcntl
import os
import time

STOP_FD_ENV = 'X4_DEV_PLAYER_STOP_FD'


def validate_option(requested, manifest):
    if type(requested) is not bool or (requested and manifest.get('worker_dispatch') is not True):
        raise ValueError('--local-stop requires a worker-dispatch bundle')
    return requested


class LocalStopChannel:
    def __init__(self, slot):
        self.slot = slot
        self.process = None
        self.read_fd = self.write_fd = None
        self.evidence = {'slot': slot, 'requested': False, 'request_written': False,
                         'returncode_before_fallback': None, 'exit225_observed': False,
                         'fallback_needed': None, 'fallback_attempted': False}
        try:
            self.read_fd, self.write_fd = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
            for name in ('read_fd', 'write_fd'):
                descriptor = getattr(self, name)
                if descriptor < 3:
                    setattr(self, name, fcntl.fcntl(descriptor, fcntl.F_DUPFD_CLOEXEC, 3))
                    os.close(descriptor)
        except BaseException:
            self.close()
            raise

    def environment(self, environment):
        result = dict(environment)
        result[STOP_FD_ENV] = str(self.read_fd)
        return result

    def close_descriptor(self, name):
        descriptor = getattr(self, name)
        setattr(self, name, None)
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as error:
                self.evidence.setdefault('close_errors', []).append(str(error))

    def close_read(self):
        self.close_descriptor('read_fd')

    def close(self):
        self.close_read()
        self.close_descriptor('write_fd')

    def request(self):
        if self.write_fd is None:
            return
        try:
            if self.process.poll() is None:
                self.evidence['requested'] = True
                try:
                    self.evidence['request_written'] = os.write(self.write_fd, b'S') == 1
                except OSError as error:
                    self.evidence['write_error'] = str(error)
        finally:
            self.close_descriptor('write_fd')


def launch_game(slot, environment, command_factory, launch, enabled):
    """Only this child's read end is inherited; parent keeps only its writer."""
    if not enabled:
        clean_environment = dict(environment)
        clean_environment.pop(STOP_FD_ENV, None)
        return launch(command_factory(clean_environment)), None
    channel = LocalStopChannel(slot)
    try:
        process = launch(command_factory(channel.environment(environment)), pass_fds=(channel.read_fd,))
        channel.process = process
        return process, channel
    except BaseException:
        channel.close()
        raise
    finally:
        channel.close_read()


def cooperative_stop(channels, timeout=2.0):
    """Request all owned local games first, then share one bounded grace window.

    Observed exit status is evidence; an S request does not establish its cause.
    The caller retains its existing owned-process fallback after this returns.
    """
    try:
        for channel in channels:
            channel.request()
        deadline = time.monotonic() + timeout
        while any(channel.process.poll() is None for channel in channels):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.02, remaining))
        for channel in channels:
            code = channel.process.poll()
            channel.evidence['returncode_before_fallback'] = code
            channel.evidence['exit225_observed'] = code == 225
            channel.evidence['fallback_needed'] = code is None
        return {str(channel.slot): dict(channel.evidence) for channel in channels}
    finally:
        for channel in channels:
            channel.close()
