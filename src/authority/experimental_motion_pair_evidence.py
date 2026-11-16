"""Validate two samples from the bounded read-only source motion diagnostic.

Actor and local sector identities are checked inside the source process; they
are deliberately absent here. This checks the portable sequence and rate, not
cross-process frame equality, atomicity or native game velocity.
"""
import math
from .experimental_tcp_motion import motion_value


def validate_pair(samples, *, epoch, generation, index, sector):
    if type(samples) is not list or len(samples)!=2:raise ValueError('exactly two samples required')
    first,second=(motion_value(x) for x in samples)
    for seq,s in enumerate((first,second),1):
        if (s['epoch']!=epoch or s['generation']!=generation or s['index']!=index or
            s['sequence']!=seq or s['sector_macro']!=sector):
            raise ValueError('motion sample identity differs')
    if first['velocity'] is not None:raise ValueError('first velocity is unknown')
    dt=second['source_time']-first['source_time']
    if not math.isfinite(dt) or dt<=0:raise ValueError('motion source time did not advance')
    velocity=second['velocity']
    if velocity is not None:
        if not .02<=dt<=1:raise ValueError('rate outside diagnostic source time interval')
        for axis in ('x','y','z'):
            estimate=(second[axis]-first[axis])/dt
            if not math.isfinite(estimate) or not math.isclose(velocity[axis],estimate,rel_tol=1e-9,abs_tol=1e-9):
                raise ValueError('rate differs from source position difference')
    return [first,second]
