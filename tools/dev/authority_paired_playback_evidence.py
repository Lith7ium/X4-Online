"""Read-only correlation of the bounded ENH-870 source/client diagnostic.

Portable registry identity is the user-approved experimental correspondence,
not independent historical identity proof. No native writes or network I/O.
"""
import copy
import math
import time

from authority.experimental_tcp_motion import check_motion_progress, motion_value
from authority_native_client_playback import EPOCH, SECTOR, PlaybackLog, PlaybackLogPending

SAMPLE_COUNT = 26
SAMPLE_INTERVAL = .2
DRAIN_SECONDS = 1.25
PREDICTION_HORIZON = .35  # Existing motion_buffer.lua default; not a new policy.


class PairedPlaybackEvidence:
    def __init__(self, path, *, guard, deadline, latest=False, sample_version=1):
        if (type(latest) is not bool or type(sample_version) is not int or sample_version not in (1, 3) or not callable(guard) or
                not math.isfinite(deadline) or deadline <= time.monotonic()):
            raise ValueError('bounded playback evidence context required')
        self.reader = PlaybackLog(path, sample_version=sample_version)
        self.guard = guard
        self.deadline = deadline
        self.latest = latest
        self.sample_version = sample_version
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
        if (value['version'] != self.sample_version or value['epoch'] != EPOCH or value['index'] != 1318 or
                value['sector_macro'] != SECTOR or not sequence_valid or
                len(self.samples) >= SAMPLE_COUNT):
            raise ValueError('paired playback source identity or sequence differs')
        if self.samples and value['generation'] != self.samples[-1]['generation']:
            raise ValueError('paired playback source lifetime or clock differs')
        check_motion_progress(value, self.samples[-1] if self.samples else None)
        if not self.samples:
            self.initial, _, _ = self._wait_for(0)
            if self.sample_version == 3:
                self._check_capture_clock(self.initial, value)
                alignment = self.initial.get('initial_alignment_clock')
                if alignment is not None:
                    self._check_capture_clock(alignment, value)
                    target = [alignment['target_' + axis] for axis in ('x', 'y', 'z')]
                    actual = [alignment['actual_' + axis] for axis in ('x', 'y', 'z')]
                    initial_pose = [self.initial[axis] for axis in ('x', 'y', 'z')]
                    readback_error = math.dist(actual, target)
                    arrival_age = alignment['local_time'] - alignment['arrival']
                    if (target != [value[axis] for axis in ('x', 'y', 'z')] or
                            alignment['tolerance'] != 3 or alignment['error'] > 3 or
                            readback_error > 3 or not math.isclose(readback_error, alignment['error'], abs_tol=1e-6) or
                            not 0 <= arrival_age < 1 or self.initial['local_time'] < alignment['local_time'] or
                            math.dist(actual, initial_pose) > 3):
                        raise ValueError('initial alignment differs from source pose or readback')
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
            if self.sample_version == 3:
                self.initial_comparison['source_capture_time'] = value['capture_time']
            if initial_offset > 50:
                raise ValueError('paired playback initial offset exceeds fixture bound')
        self.samples.append(value)
        return True

    @staticmethod
    def _check_capture_clock(row, sample):
        clock = row.get('capture_clock')
        if (type(clock) is not dict or clock['latest_source_time'] != sample['source_time'] or
                clock['latest_capture_time'] != sample['capture_time']):
            raise ValueError('paired playback source capture clocks differ')

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
        velocity = final['real_velocity'] if self.sample_version == 3 else final['velocity']
        if (stopped['source_sequence'] != final['sequence'] or stopped['samples'] != sample_count or
                stopped['readbacks'] < 2 or stopped['phase'] != 'frozen' or velocity is None):
            raise ValueError('paired playback final sample not observed')
        acknowledged_ordinals = {sample['sequence']: ordinal
                                 for ordinal, sample in enumerate(self.samples, 1)}
        for row in [*summaries, stopped]:
            if self.latest or self.sample_version == 3:
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
            if self.sample_version == 3:
                if row is stopped:
                    self._check_capture_clock(row, final)
                else:
                    # A readback can describe a previous write after a newer
                    # BIND. Its clocks must identify an acknowledged sample
                    # already delivered by this row, at or beyond its render.
                    clock = row['capture_clock']
                    matching = [sample for sample in self.samples[:row['samples']]
                                if sample['source_time'] == clock['latest_source_time'] and
                                sample['capture_time'] == clock['latest_capture_time'] and
                                sample['sequence'] >= row['source_sequence']]
                    if len(matching) != 1:
                        raise ValueError('paired playback source capture clocks differ')
        predicted = [final[axis] + velocity[axis] * PREDICTION_HORIZON for axis in ('x', 'y', 'z')]
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
        if self.sample_version == 3:
            result.update(sample_version=3, clock_basis='capture_time',
                          source_capture_elapsed=final['capture_time'] - self.samples[0]['capture_time'],
                          capture_clocks_correlated=True)
        return result
