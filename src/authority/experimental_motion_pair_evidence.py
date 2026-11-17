"""Validate two samples from the bounded read-only source motion diagnostic.

Actor and local sector identities are checked inside the source process; they
are deliberately absent here. This checks the portable sequence and rate, not
cross-process frame equality, atomicity or native game velocity.
"""
import math

from .experimental_tcp_motion import motion_value


def validate_pair(samples, *, epoch, generation, index, sector):
    if type(samples) is not list or len(samples) != 2:
        raise ValueError('exactly two samples required')
    first, second = (motion_value(sample) for sample in samples)
    for sequence, sample in enumerate((first, second), 1):
        if (sample['epoch'] != epoch or sample['generation'] != generation or
                sample['index'] != index or sample['sequence'] != sequence or
                sample['sector_macro'] != sector):
            raise ValueError('motion sample identity differs')
    if first['velocity'] is not None:
        raise ValueError('first velocity is unknown')
    if first['version'] != second['version']:
        raise ValueError('motion sample version changed')
    elapsed_seconds = second['source_time'] - first['source_time']
    if not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0:
        raise ValueError('motion source time did not advance')
    velocity = second['velocity']
    if velocity is not None:
        if not .02 <= elapsed_seconds <= 1:
            raise ValueError('rate outside diagnostic source time interval')
        for axis in ('x','y','z'):
            estimate = (second[axis] - first[axis]) / elapsed_seconds
            if (not math.isfinite(estimate) or
                    not math.isclose(velocity[axis], estimate, rel_tol=1e-9, abs_tol=1e-9)):
                raise ValueError('rate differs from source position difference')
    if second['version'] == 2 and second['angular_rate'] is not None:
        for axis in ('yaw','pitch','roll'):
            delta = (second['orientation'][axis] - first['orientation'][axis] + math.pi) % (2 * math.pi) - math.pi
            estimate = delta / elapsed_seconds
            if not math.isclose(second['angular_rate'][axis], estimate, rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError('angular rate differs from orientation difference')
    return [first, second]
