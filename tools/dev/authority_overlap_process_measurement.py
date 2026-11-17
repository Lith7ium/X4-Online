"""Optional process measurement between the first and second overlap admissions."""
import hashlib
import json
import os

from authority.linux_proc_measurement import measure_running_window
from authority.linux_proc_sampler import LinuxProcSampler


def measure_single_client_phase(*, server_identity, client_identity, supervisor_identity,
                                clock, tick, check, duration, deadline):
    """Observe owned PIDs while the server clock and membership are checked.

    File-guard hashing and test traffic remain active. Their resource use is
    diagnostic overhead; the supervisor measurements help quantify part of it.
    The successful result is still subject to the enclosing run's final checks.
    """
    sampler = LinuxProcSampler({'server_x4': server_identity, 'client_x4': client_identity,
                                'supervisor': supervisor_identity})
    checks = 0
    def checked_context():
        nonlocal checks
        checks += 1
        return check()
    def read_clock():
        return clock.sample(deadline, tick, checked_context)
    result = measure_running_window(enabled=True, sampler=sampler, read_running_game_time=read_clock,
        tick=tick, check=checked_context, duration_seconds=duration, deadline=deadline)
    if (result['elapsed_seconds'] < duration or len(result['samples']) < 4 or
            any(sample['interval_seconds'] is None for sample in result['samples'][1:])):
        raise ValueError('running process measurement is too short')
    result['process_identities'] = {name: {'pid': identity[0], 'start_ticks': identity[1]}
                                    for name, identity in (('server_x4', server_identity),
                                                           ('client_x4', client_identity),
                                                           ('supervisor', supervisor_identity))}
    result.update(owner_context_checks=checks,
                  diagnostic_cpu_and_io_included=True, windows_tested=False,
                  gameplay_proven=False, exact_loaded_file_proven=False,
                  phase='after_first_admission_before_second_join',
                  enclosing_run_final_checks_required=True)
    return result


def write_report(out, result):
    """Publish one complete private report without overwriting an existing file."""
    payload = (json.dumps(result, indent=2, allow_nan=False) + '\n').encode('utf-8')
    temporary = out / 'process-measurement.json.tmp'
    final = out / 'process-measurement.json'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, final, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)
    return {'report': final.name, 'sha256': hashlib.sha256(payload).hexdigest(),
            'phase': result['phase'], 'game_time_before': result['game_time_before'],
            'game_time_after': result['game_time_after'], 'elapsed_seconds': result['elapsed_seconds'],
            'sample_count': len(result['samples']), 'process_identities': result['process_identities'],
            'save_guard_mode': result.get('save_guard_mode'),
            'diagnostic_cpu_and_io_included': result.get('diagnostic_cpu_and_io_included'),
            'enclosing_run_final_checks_required': True}
