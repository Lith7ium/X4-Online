"""One-shot participant motion bridge, created only after local resume."""

from .experimental_tcp_motion import check_motion_progress, motion_value

RECOVERY_SETTER_FIXTURE = 'recovery_enh_870'
RECOVERY_SETTER_EPOCH = '4ba7be438ebb04ec5bb85fdb95b5a488'
RECOVERY_SETTER_INDEX = 1318


class ParticipantMotion:
    """Bind the first resumed sample and fence motion until remote STOP."""

    def __init__(self, sock, config, guard, validate_peer, ipc_factory=None):
        self.sock = sock
        self.config = config
        self.guard = guard
        self.validate_peer = validate_peer
        self.ipc_factory = ipc_factory
        self.running = False
        self.stopped = False
        self.bridge = None
        self.destination = sock.getsockname()
        self._playback_previous = None
        self._confirmed_samples = 0
        self._timeout = config['motion']['timeout']

    @property
    def timeout(self):
        """The fixed IPC deadline used by session command budgeting."""
        return self._timeout

    @property
    def confirmed_samples(self):
        """Number of source samples whose local IPC receipt was confirmed."""
        return self._confirmed_samples

    def _bind(self):
        if self.guard() is not True:
            raise RuntimeError('motion owner guard failed')
        if self.bridge is None:
            ipc_factory = self.ipc_factory
            if ipc_factory is None:
                from .experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC
                ipc_factory = ExperimentalParticipantMotionIPC
            motion_config = self.config['motion']
            self.bridge = ipc_factory(
                self.sock,
                enabled=True,
                lease=motion_config['lease'],
                attempt=motion_config['attempt'],
                epoch=motion_config['epoch'],
                generation=motion_config['generation'],
                guard=lambda: (self.running and self.sock.getsockname() == self.destination and
                               self.guard() is True),
                validate_peer=self.validate_peer,
                timeout=self._timeout,
                allow_apply=motion_config.get('saved_apply_fixture') == RECOVERY_SETTER_FIXTURE,
                stop_enabled=True,
            )
            self.bridge.wait_ready()
        if self.guard() is not True:
            raise RuntimeError('motion owner guard failed')

    def __call__(self, sample, despawn):
        if not self.running or self.stopped or despawn is not False:
            raise RuntimeError('motion while paused or unsupported despawn')
        playback = self.config['motion'].get('saved_playback_fixture') == RECOVERY_SETTER_FIXTURE
        if playback:
            sample = motion_value(sample)
            motion_config = self.config['motion']
            if (sample['version'] not in (1, 3) or sample['epoch'] != RECOVERY_SETTER_EPOCH or
                    sample['generation'] != motion_config['generation'] or
                    sample['index'] != RECOVERY_SETTER_INDEX or
                    sample['sector_macro'] != 'cluster_06_sector001_macro'):
                raise ValueError('recovery playback sample mismatch')
            previous = self._playback_previous
            if previous is None:
                # The first actual source sample enrolls; never fabricate its clock or sequence.
                if sample['sequence'] != 1:
                    raise ValueError('recovery playback must enroll source sequence one')
            else:
                if sample['sequence'] <= previous['sequence']:
                    raise ValueError('recovery playback source regressed')
                check_motion_progress(sample, previous)
        self._bind()
        confirmed = self.bridge(sample, despawn)
        if confirmed is True:
            self._confirmed_samples += 1
        if playback and confirmed is True:
            self._playback_previous = sample
        return confirmed

    def _check_setter_sample(self, sample):
        """Fence the only permitted recovery fixture before any setter IPC."""
        motion_config = self.config['motion']
        if (not self.running or self.stopped or
                motion_config.get('saved_apply_fixture') != RECOVERY_SETTER_FIXTURE):
            raise RuntimeError('recovery setter unavailable')
        if (type(sample) is not dict or sample.get('version') != 1 or sample.get('epoch') != RECOVERY_SETTER_EPOCH or
                type(sample.get('index')) is not int or sample['index'] != RECOVERY_SETTER_INDEX or
                sample.get('generation') != motion_config['generation']):
            raise ValueError('recovery setter sample mismatch')

    def preflight(self, sample):
        self._check_setter_sample(sample)
        self._bind()
        return self.bridge.preflight(sample)

    def apply_once(self, sample):
        self._check_setter_sample(sample)
        self._bind()
        return self.bridge.apply_once(sample)

    def before_control(self, operation):
        if operation not in ('pause', 'resume'):
            raise ValueError('unsupported participant control operation')
        if operation == 'resume':
            if self.stopped:
                raise RuntimeError('stopped motion lease cannot resume')
            return True
        return self.stop()

    def after_control(self, operation):
        if operation not in ('pause', 'resume'):
            raise ValueError('unsupported participant control operation')
        if operation == 'resume':
            if self.stopped:
                raise RuntimeError('stopped motion lease cannot resume')
            self.running = True
        return True

    def stop(self):
        if self.stopped:
            return True
        if not self.running:
            raise RuntimeError('motion stop cannot be confirmed before resume')
        self._bind()
        if self.bridge.stop_remote() is not True:
            raise RuntimeError('client motion stop unconfirmed')
        self.running = False
        self.stopped = True
        return True

    def close(self):
        if self.bridge is None:
            self.sock.close()
        elif self.bridge.state not in ('closed', 'failed'):
            self.bridge.close()
