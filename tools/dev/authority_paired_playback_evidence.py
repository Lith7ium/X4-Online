"""Read-only correlation of the bounded ENH-870 source/client diagnostic.

Portable registry identity is the user-approved experimental correspondence,
not independent historical identity proof. No native writes or network I/O.
"""
import copy
import math
import time

from authority.experimental_tcp_motion import motion_value
from authority_native_client_playback import EPOCH, SECTOR, PlaybackLog, PlaybackLogPending

SAMPLE_COUNT = 26
SAMPLE_INTERVAL = .2
DRAIN_SECONDS = 1.25
PREDICTION_HORIZON = .35  # Existing motion_buffer.lua default; not a new policy.


class PairedPlaybackEvidence:
    def __init__(self, path, *, guard, deadline):
        if not callable(guard) or not math.isfinite(deadline) or deadline <= time.monotonic():
            raise ValueError('bounded playback evidence context required')
        self.reader = PlaybackLog(path)
        self.guard = guard
        self.deadline = deadline
        self.samples = []
        self.initial = None

    def _wait_for(self, field, *, guard=None):
        check = self.guard if guard is None else guard
        if not callable(check):
            raise ValueError('playback evidence guard required')
        deadline = min(self.deadline, time.monotonic() + 5)
        while True:
            if check() is not True or time.monotonic() >= deadline:
                raise RuntimeError('playback evidence guard or deadline failed')
            try:
                records = self.reader.read()
                if records[field] is not None:
                    return records
            except PlaybackLogPending:
                pass
            time.sleep(.01)

    def received(self, sample):
        """Called after its TCP receipt; first source packet only enrolled X4."""
        value = motion_value(sample)
        if (value['version'] != 1 or value['epoch'] != EPOCH or value['index'] != 1318 or
                value['sector_macro'] != SECTOR or value['sequence'] != len(self.samples) + 1 or
                len(self.samples) >= SAMPLE_COUNT):
            raise ValueError('paired playback source identity or sequence differs')
        if self.samples and (value['generation'] != self.samples[-1]['generation'] or
                             value['source_time'] <= self.samples[-1]['source_time']):
            raise ValueError('paired playback source lifetime or clock differs')
        if not self.samples:
            self.initial, _, _ = self._wait_for(0)
            if math.dist([value[axis] for axis in ('x', 'y', 'z')],
                         [self.initial[axis] for axis in ('x', 'y', 'z')]) > 50:
                raise ValueError('paired playback initial offset exceeds fixture bound')
        self.samples.append(value)
        return True

    def stopped(self, *, stopped_guard):
        """Validate native drain and the final source-derived predicted target."""
        initial, summaries, stopped = self._wait_for(2, guard=stopped_guard)
        if len(self.samples) != SAMPLE_COUNT or initial != self.initial or not summaries:
            raise ValueError('paired playback evidence incomplete')
        final = self.samples[-1]
        if (stopped['source_sequence'] != final['sequence'] or stopped['samples'] != SAMPLE_COUNT or
                stopped['readbacks'] < 2 or stopped['phase'] != 'frozen' or final['velocity'] is None):
            raise ValueError('paired playback final sample not observed')
        for row in [*summaries, stopped]:
            if (not 2 <= row['source_sequence'] <= SAMPLE_COUNT or
                    not row['source_sequence'] <= row['samples'] <= SAMPLE_COUNT or row['error'] > 3):
                raise ValueError('paired playback readback mismatch')
        predicted = [final[axis] + final['velocity'][axis] * PREDICTION_HORIZON for axis in ('x', 'y', 'z')]
        target = [stopped['target_' + axis] for axis in ('x', 'y', 'z')]
        actual = [stopped['actual_' + axis] for axis in ('x', 'y', 'z')]
        if math.dist(predicted, target) > .05 or math.dist(actual, target) > 3:
            raise ValueError('paired playback target differs from source prediction')
        source_movement = math.dist([self.samples[0][axis] for axis in ('x', 'y', 'z')],
                                    [final[axis] for axis in ('x', 'y', 'z')])
        client_movement = math.dist([initial[axis] for axis in ('x', 'y', 'z')], actual)
        if source_movement <= .02 or client_movement <= .02:
            raise ValueError('paired playback movement unconfirmed')
        return dict(initial=copy.deepcopy(initial), stopped=copy.deepcopy(stopped),
                    source_samples=SAMPLE_COUNT, source_displacement=source_movement,
                    client_displacement=client_movement, target_prediction_error=math.dist(predicted, target),
                    source_game_elapsed=final['source_time'] - self.samples[0]['source_time'],
                    client_game_elapsed=stopped['game_time'] - initial['game_time'],
                    native_position_changed=True, native_velocity_proven=False,
                    cross_process_identity_proven=False)
