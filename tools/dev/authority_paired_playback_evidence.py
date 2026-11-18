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
    def __init__(self, path, *, guard, deadline, latest=False):
        if (type(latest) is not bool or not callable(guard) or
                not math.isfinite(deadline) or deadline <= time.monotonic()):
            raise ValueError('bounded playback evidence context required')
        self.reader = PlaybackLog(path)
        self.guard = guard
        self.deadline = deadline
        self.latest = latest
        self.samples = []
        self.initial = None
        self.initial_comparison = None

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
                if check() is not True or time.monotonic() >= deadline:
                    raise RuntimeError('playback evidence guard or deadline failed')
                if records[field] is not None:
                    return records
            except PlaybackLogPending:
                pass
            time.sleep(.01)

    def received(self, sample):
        """Record an acknowledged original sample; latest callers defer log reads until drain."""
        value = motion_value(sample)
        expected_sequence = len(self.samples) + 1
        sequence_valid = value['sequence'] == expected_sequence
        if self.latest:
            previous_sequence = self.samples[-1]['sequence'] if self.samples else 0
            sequence_valid = (previous_sequence < value['sequence'] <= SAMPLE_COUNT and
                              (bool(self.samples) or value['sequence'] == 1))
        if (value['version'] != 1 or value['epoch'] != EPOCH or value['index'] != 1318 or
                value['sector_macro'] != SECTOR or not sequence_valid or
                len(self.samples) >= SAMPLE_COUNT):
            raise ValueError('paired playback source identity or sequence differs')
        if self.samples and (value['generation'] != self.samples[-1]['generation'] or
                             value['source_time'] <= self.samples[-1]['source_time']):
            raise ValueError('paired playback source lifetime or clock differs')
        if not self.samples:
            self.initial, _, _ = self._wait_for(0)
            initial_offset = math.dist([value[axis] for axis in ('x', 'y', 'z')],
                                       [self.initial[axis] for axis in ('x', 'y', 'z')])
            # Retain this bounded comparison even when admission fails. A
            # receipt is not an accepted movement sample, and a failure must
            # not lose the positions needed to investigate that distinction.
            self.initial_comparison = {
                **{'source_' + axis: value[axis] for axis in ('x', 'y', 'z')},
                **{'client_' + axis: self.initial[axis] for axis in ('x', 'y', 'z')},
                'source_game_time': value['source_time'],
                'client_game_time': self.initial['game_time'],
                'client_local_time': self.initial['local_time'],
                'offset_metres': initial_offset, 'limit_metres': 50,
                'within_bound': initial_offset <= 50,
            }
            if initial_offset > 50:
                raise ValueError('paired playback initial offset exceeds fixture bound')
        self.samples.append(value)
        return True

    def stopped(self, *, stopped_guard):
        """Validate native drain and the final source-derived predicted target."""
        initial, summaries, stopped = self._wait_for(2, guard=stopped_guard)
        sample_count = len(self.samples)
        complete = sample_count == SAMPLE_COUNT
        if self.latest:
            complete = sample_count >= 2 and self.samples[-1]['sequence'] == SAMPLE_COUNT
        if not complete or initial != self.initial or not summaries:
            raise ValueError('paired playback evidence incomplete')
        final = self.samples[-1]
        if (stopped['source_sequence'] != final['sequence'] or stopped['samples'] != sample_count or
                stopped['readbacks'] < 2 or stopped['phase'] != 'frozen' or final['velocity'] is None):
            raise ValueError('paired playback final sample not observed')
        acknowledged_ordinals = {sample['sequence']: ordinal
                                 for ordinal, sample in enumerate(self.samples, 1)}
        for row in [*summaries, stopped]:
            if self.latest:
                # Interpolation may still report an earlier acknowledged source
                # after later deliveries. Its count must include that delivery.
                ordinal = acknowledged_ordinals.get(row['source_sequence'])
                count_valid = ordinal is not None and ordinal <= row['samples'] <= sample_count
            else:
                count_valid = (2 <= row['source_sequence'] <= SAMPLE_COUNT and
                               row['source_sequence'] <= row['samples'] <= SAMPLE_COUNT)
            if (not count_valid or row['error'] > 3 or
                    math.dist([row['actual_' + axis] for axis in ('x', 'y', 'z')],
                              [row['target_' + axis] for axis in ('x', 'y', 'z')]) > 3):
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
        result = dict(initial=copy.deepcopy(initial), stopped=copy.deepcopy(stopped),
                    source_samples=sample_count, source_displacement=source_movement,
                    client_displacement=client_movement, target_prediction_error=math.dist(predicted, target),
                    source_game_elapsed=final['source_time'] - self.samples[0]['source_time'],
                    client_game_elapsed=stopped['game_time'] - initial['game_time'],
                    native_position_changed=True, native_velocity_proven=False,
                    cross_process_identity_proven=False)
        if self.latest:
            result.update(latest=True, acknowledged_sequences=list(acknowledged_ordinals),
                          final_source_sequence=final['sequence'])
        return result
