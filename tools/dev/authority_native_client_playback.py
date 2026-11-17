"""Optional, pinned one-fixture playback for the independent native client.

A trusted Python-only driver supplies a finite synthetic path. The worker owns
only local motion UDP; it never polls the TCP client owner or native controller.
This is internal client evidence, not a server or synchronized-world test.
"""
import copy
import hashlib
import json
import math
import os
import queue
from pathlib import Path
import secrets
import socket
import threading
import time

from authority.experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC
from authority.load_messages import _pairs, _reject_constant
from authority_tcp_job_client_live import socket_owner
from authority_tcp_native_worker import check_process
import authority_recovered_client_motion_install as motion_install
import authority_recovered_client_registry as registry

EPOCH = '4ba7be438ebb04ec5bb85fdb95b5a488'
STATUS = ('ready', EPOCH, 10082, '4498b099b8741fccbe1f189cbcb7e8da5a7b08de48d7d57e0caf95baa692e72a')
SAVE_SHA = '2b07a55d0d5fda0ef08de8a6b9a562100d745ae39076d1a7092f5e3c150f5994'
MARKER = 'a41d7cba34dc95f0c2ce73d4a02655fc'
CONTENT_SHA = '4785ab88f8e53a94b6174c4a3fcd99ca9ef94fc3c39b27244300c2ba248b2710'
SCRIPT_PINS = {
    'authority_checkpoint_marker.xml': '6de4be69d19601a02a96e5e7f2285f9d14dfceab9dc9cccb82909b9444625813',
    'authority_identity_fixture.xml': '92b515e7f3e47a29762e084ad6d0fe0239e5ba34993c08a63b5c610aeb92dd43',
    'authority_registry_witness.xml': 'b29134477dd3bcad103a325f6295b935217a639fb79a197bfaffc4103ea9a096',
    'authority_ship_registry.xml': 'b39c8cfad274f74411cd2b518976f7d343c9c43666d8c9a8a8dc62b55443b0af',
}
SECTOR = 'cluster_06_sector001_macro'
TAG = b'[X4LAN] AUTH_CLIENT_PLAYBACK '
MAX_LOG = 8 * 1024 * 1024


def read_config(path, args, driver):
    """Reject unknown lineage/fields and compatibility conflicts before mutation."""
    if path is None:
        if driver is not None:
            raise ValueError('playback_config_required')
        return None
    if not callable(driver):
        raise ValueError('playback_python_driver_required')
    if any(getattr(args, name, None) is not None for name in
           ('archived_identity_fixture', 'archived_identity_fixture_sha256', 'expected_content_sha256')):
        raise ValueError('playback_compatibility_options_conflict')
    evidence = registry.recovery.marked.file_evidence
    raw = evidence._read_regular(path, 16384, collect=True)[2]
    try:
        config = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError('invalid_playback_config') from None
    expected = {'version': 1, 'fixture': 'recovery_enh_870', 'checkpoint_sha256': SAVE_SHA,
                'registry_status': list(STATUS), 'content_sha256': CONTENT_SHA}
    if type(config) is not dict or set(config) != set(expected)|{'scripts'} or any(
            type(config[k]) is not type(value) or config[k] != value for k, value in expected.items()):
        raise ValueError('invalid_playback_config')
    if any(type(actual) is not type(value) for actual, value in zip(config['registry_status'], STATUS)):
        raise ValueError('invalid_playback_config')
    if type(config['scripts']) is not dict or set(config['scripts']) != set(SCRIPT_PINS):
        raise ValueError('invalid_playback_scripts')
    scripts = {}
    for name, pin in SCRIPT_PINS.items():
        entry = config['scripts'][name]
        if (type(entry) is not dict or set(entry) != {'path', 'sha256'} or entry['sha256'] != pin or
                type(entry['path']) is not str or not Path(entry['path']).is_absolute()):
            raise ValueError('invalid_playback_scripts')
        data = evidence._read_regular(Path(entry['path']), 1 << 20, collect=True)[2]
        if hashlib.sha256(data).hexdigest() != pin:
            raise ValueError('playback_script_pin_differs')
        scripts[name] = data
    return scripts


def install(case, profile, bound, ticket, participant, scripts, driver, deadline, out):
    if (bound.offer.sha256 != SAVE_SHA or bound.offer.size != 26183913 or bound.marker != MARKER or
            hashlib.sha256((profile/'content.xml').read_bytes()).hexdigest() != CONTENT_SHA):
        raise ValueError('playback_offered_source_differs')
    lab = case/'extensions/x4_lan_lab'
    # Validate compatibility and all destination collisions before any writes.
    for name, data in scripts.items():
        target = lab/'md'/name
        if target.is_symlink() or (target.exists() and target.read_bytes() != data):
            raise ValueError('playback_script_destination_differs')
    for name in ('authority_checkpoint_marker.xml', 'authority_ship_registry.xml'):
        source = motion_install.ROOT/('src/authority/md/checkpoint_marker.xml' if name.startswith('authority_checkpoint') else 'tools/dev/'+name)
        if hashlib.sha256(source.read_bytes()).hexdigest() != SCRIPT_PINS[name]:
            raise ValueError('playback_current_script_differs')
    excluded = {participant.lease, ticket['world_epoch'], ticket['attempt_id'], EPOCH,
                ticket['checkpoint_id'].removeprefix('checkpoint-')}
    def token():
        value = secrets.token_hex(16)
        while value in excluded:
            value = secrets.token_hex(16)
        excluded.add(value)
        return value
    nonce = token()
    protected = registry.install(case, nonce, STATUS, load_gate='marker')
    for name, data in scripts.items():
        target = lab/'md'/name
        if not target.exists():
            with target.open('xb') as stream:
                stream.write(data)
        protected.append(target)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(('127.0.0.1', 0))
        settings = dict(port=sock.getsockname()[1], index=1318, timeout=5,
                        saved_playback_fixture='recovery_enh_870',
                        **{key: token() for key in ('lease', 'attempt', 'generation', 'nonce', 'router_generation')})
        installation = motion_install.install(case, profile, STATUS, settings)
        return Playback(sock, settings, installation, nonce, ticket, bound.marker, driver, deadline,
                        profile/'engine-output.log', out, [*protected, *installation.paths])
    except BaseException:
        sock.close()
        raise


def _number(text, *, integer=False):
    try:
        value = float(text)
    except (ValueError, OverflowError):
        raise ValueError('invalid_playback_log_number') from None
    if not math.isfinite(value) or abs(value) > 1e12 or (integer and (value < 0 or value % 1)):
        raise ValueError('invalid_playback_log_number')
    return int(value) if integer else value


class PlaybackLogPending(ValueError):
    """Only append/incomplete snapshots may be retried within bounded waits."""


def parse_records(data):
    """Parse bounded, fixed-field native readbacks; BOUND is not a position ACK."""
    if len(data) > MAX_LOG or (data and not data.endswith(b'\n')):
        raise ValueError('invalid_playback_log')
    if b'AUTH_RECOVERED_CLIENT_MOTION ERROR' in data:
        raise ValueError('native_playback_faulted')
    initial, summaries, stopped = None, [], None
    last_local = last_game = -1
    for line in data.splitlines():
        if len(line) > 16384:
            raise ValueError('playback_log_line_too_long')
        if TAG not in line:
            continue
        try:
            kind, *items = line.split(TAG, 1)[1].decode('ascii').split()
            fields = dict(item.split('=', 1) for item in items)
        except (ValueError, UnicodeError):
            raise ValueError('invalid_playback_record') from None
        if len(fields) != len(items) or stopped is not None:
            raise ValueError('duplicate_or_late_playback_record')
        common = {'version', 'epoch', 'index', 'sector', 'source_sequence', 'local_time', 'game_time'}
        numeric = {'x', 'y', 'z'} if kind == 'INITIAL' else {
            'actual_x', 'actual_y', 'actual_z', 'target_x', 'target_y', 'target_z', 'error'}
        extra = set() if kind == 'INITIAL' else {'report', 'samples', 'observations', 'readbacks', 'phase'}
        if kind == 'STOPPED':
            extra.update(('uncertain', 'drained'))
        if (kind not in ('INITIAL', 'SUMMARY', 'STOPPED') or set(fields) != common|numeric|extra or
                fields['version'] != '1' or fields['epoch'] != EPOCH or fields['index'] != '1318' or fields['sector'] != SECTOR):
            raise ValueError('foreign_playback_record')
        for key in numeric|{'local_time', 'game_time'}:
            fields[key] = _number(fields[key])
        for key in {'source_sequence'}|({'report', 'samples', 'observations', 'readbacks'} if kind != 'INITIAL' else set()):
            fields[key] = _number(fields[key], integer=True)
        if fields['local_time'] < 0 or fields['game_time'] < 0 or fields['local_time'] < last_local or fields['game_time'] < last_game:
            raise ValueError('regressed_playback_clock')
        last_local, last_game = fields['local_time'], fields['game_time']
        if kind == 'INITIAL':
            if initial is not None or summaries or fields['source_sequence'] != 1:
                raise ValueError('duplicate_playback_initial')
            initial = fields
        else:
            if initial is None or fields['error'] < 0 or fields['phase'] not in (
                    'held', 'interpolated', 'extrapolated', 'frozen', 'held-no-rate', 'waiting'):
                raise ValueError('invalid_playback_summary')
            if kind == 'SUMMARY':
                if len(summaries) >= 64:
                    raise ValueError('too_many_playback_summaries')
                if fields['report'] != len(summaries)+1:
                    raise ValueError('invalid_playback_report_counter')
                summaries.append(fields)
            else:
                if fields['uncertain'] != '0' or fields['drained'] != '1' or fields['report'] != len(summaries):
                    raise ValueError('uncertain_native_playback_stop')
                stopped = fields
    return initial, summaries, stopped


def validate_plan(initial, driver):
    """Materialize at most 64 bounded synthetic XYZ samples on the worker."""
    records, previous = [], 0
    for raw in driver(copy.deepcopy(initial)):
        if len(records) >= 64 or type(raw) is not dict or set(raw) != {'after', 'x', 'y', 'z', 'velocity'}:
            raise ValueError('invalid_playback_driver_plan')
        sample = copy.deepcopy(raw)
        if (type(sample['after']) not in (int, float) or not math.isfinite(sample['after']) or
                not previous < sample['after'] <= 10 or type(sample['velocity']) is not dict or
                set(sample['velocity']) != {'x', 'y', 'z'}):
            raise ValueError('invalid_playback_driver_plan')
        for axis in ('x', 'y', 'z'):
            if (type(sample[axis]) not in (int, float) or not math.isfinite(sample[axis]) or
                    abs(sample[axis]-initial[axis]) > 25 or type(sample['velocity'][axis]) not in (int, float) or
                    not math.isfinite(sample['velocity'][axis]) or abs(sample['velocity'][axis]) > 5):
                raise ValueError('unbounded_playback_driver_plan')
        records.append(sample)
        previous = sample['after']
    if len(records) < 2:
        raise ValueError('insufficient_playback_driver_samples')
    return records


class Playback:
    def __init__(self, sock, settings, installation, registry_nonce, ticket, marker,
                 driver, deadline, log, out, paths):
        self.sock, self.settings, self.installation = sock, settings, installation
        self.registry_nonce, self.ticket, self.marker = registry_nonce, dict(ticket), marker
        self.driver, self.deadline, self.log, self.out = driver, deadline, log, out
        self.paths = paths
        self.thread = None
        self.abort, self.release, self.stopped = threading.Event(), threading.Event(), threading.Event()
        self.messages = queue.Queue(maxsize=2)
        self.evidence = dict(enabled=True, worker_joined=False, stopped_confirmed=False,
                             native_velocity_proven=False, native_server_tested=False)
        self.failure = None
        self._log_identity = None
        self._log_bytes = b''

    def verify_registry(self):
        return registry.verify_log(self.log, self.registry_nonce, STATUS, self.ticket, self.marker, load_gate='marker')

    def records(self):
        evidence = registry.recovery.marked.file_evidence
        def check_snapshot(identity, data):
            if self._log_identity is not None and identity != self._log_identity:
                raise ValueError('playback_log_replaced')
            if not data.startswith(self._log_bytes):
                raise ValueError('playback_log_truncated_or_rewritten')
            if b'AUTH_RECOVERED_CLIENT_MOTION ERROR' in data:
                raise ValueError('native_playback_faulted')
        def read():
            try:
                return evidence._read_regular(self.log, MAX_LOG, collect=True)
            except evidence.EvidenceFileGrowing as error:
                check_snapshot(error.fingerprint[:2], error.partial)
                raise PlaybackLogPending('playback_log_appending') from None
        before = read()
        check_snapshot(before[0][:2], before[2])
        after = read()
        check_snapshot(after[0][:2], after[2])
        if after != before:
            if after[0][:2] == before[0][:2] and len(after[2]) > len(before[2]) and after[2].startswith(before[2]):
                raise PlaybackLogPending('playback_log_appending')
            raise ValueError('playback_log_changed')
        if before[2] and not before[2].endswith(b'\n'):
            raise PlaybackLogPending('playback_log_line_pending')
        result = parse_records(before[2])
        self._log_identity, self._log_bytes = before[0][:2], before[2]
        return result

    def start(self, process, protected):
        if self.thread is not None:
            raise RuntimeError('playback_worker_already_started')
        process, protected = dict(process), dict(protected)
        self.thread = threading.Thread(target=self._worker, args=(process, protected), daemon=True)
        self.thread.start()

    def _worker(self, process, protected):
        ipc = None
        phase = 'ready'
        next_file_check = 0
        def guard():
            nonlocal next_file_check
            if self.abort.is_set() or time.monotonic() >= self.deadline:
                raise RuntimeError('playback_worker_fenced')
            check_process(process)
            if time.monotonic() >= next_file_check:
                evidence = registry.recovery.marked.file_evidence
                if any(evidence._read_regular(path, 1 << 20, collect=False)[1] != digest
                       for path, digest in protected.items()):
                    raise ValueError('playback_protected_file_changed')
                next_file_check = time.monotonic()+.25
            return True
        def peer(address):
            guard()
            return socket_owner(address, self.sock.getsockname(), process)
        def wait_until(when):
            while time.monotonic() < when:
                guard()
                self.abort.wait(min(.05, when-time.monotonic()))
        try:
            ipc = ExperimentalParticipantMotionIPC(self.sock, enabled=True,
                **{key: self.settings[key] for key in ('lease', 'attempt', 'generation')},
                epoch=EPOCH, timeout=5, guard=guard, validate_peer=peer, stop_enabled=True)
            ipc.wait_ready()
            base = dict(version=1, epoch=EPOCH, generation=self.settings['generation'], index=1318,
                        sequence=1, sector_macro=SECTOR, source_time=0, x=0, y=0, z=0, velocity=None)
            phase = 'initial'
            ipc(base, False)  # Enrollment only; runtime explicitly discards this pose.
            deadline = min(self.deadline, time.monotonic()+5)
            initial = None
            while initial is None:
                guard()
                try:
                    initial, _, _ = self.records()
                except PlaybackLogPending:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError('playback_initial_not_observed')
                self.abort.wait(.01)
            origin = time.monotonic()
            phase = 'driver'
            samples = validate_plan(initial, self.driver)
            for sequence, sample in enumerate(samples, 2):
                wait_until(origin+sample['after'])
                packet = dict(base, sequence=sequence, source_time=initial['game_time']+sample['after'],
                              **{key: sample[key] for key in ('x', 'y', 'z', 'velocity')})
                ipc(packet, False)
            phase = 'stop'
            # Runtime max_age is min(timeout, 1). Silence lets the next native
            # callback read back the final write, then stop writing on hard age.
            wait_until(time.monotonic()+1.25)
            ipc.stop_remote()
            deadline = min(self.deadline, time.monotonic()+5)
            stopped = None
            while stopped is None:
                guard()
                try:
                    initial, summaries, stopped = self.records()
                except PlaybackLogPending:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError('playback_stop_summary_missing')
                self.abort.wait(.01)
            reads = [*summaries, stopped]
            if (not summaries or max(row['readbacks'] for row in reads) < 2 or
                    max(row['error'] for row in reads) > 3 or
                    not any(math.dist([initial[a] for a in ('x', 'y', 'z')],
                                      [row['actual_'+a] for a in ('x', 'y', 'z')]) > .02 for row in reads)):
                raise ValueError('native_playback_movement_unconfirmed')
            self.messages.put_nowait(dict(initial=initial, summaries=summaries, stopped=stopped,
                delivered_samples=len(samples), stopped_confirmed=True, native_position_changed=True))
            self.stopped.set()
            # Keep IPC teardown on its owner thread, after the main owner has
            # fenced X4. TCP/participant objects are never called from here.
            self.release.wait()
            ipc.close()
        except BaseException as error:
            self.messages.put_nowait(dict(failure_phase=phase, failure_type=type(error).__name__))
        finally:
            ipc = None

    def poll(self):
        while True:
            try:
                message = self.messages.get_nowait()
            except queue.Empty:
                break
            self.evidence.update(message)
            if 'failure_phase' in message:
                self.failure = RuntimeError('native_playback_worker_failed')
            if message.get('stopped_confirmed'):
                temporary = self.out/'playback-stopped.tmp'
                with temporary.open('x', encoding='utf-8') as stream:
                    json.dump(self.evidence, stream)
                    stream.write('\n')
                # Hard linking publishes complete bytes and refuses an existing
                # destination; the host never sees a partially written receipt.
                os.link(temporary, self.out/'playback-stopped.json')
                temporary.unlink()
        if self.failure is not None:
            raise self.failure
        return self.stopped.is_set()

    def before_pause(self):
        self.poll()
        if not self.stopped.is_set():
            raise RuntimeError('native_pause_requires_playback_stopped')

    def finish(self):
        self.poll()
        if not self.stopped.is_set():
            raise RuntimeError('native_playback_not_stopped')
        self.records()  # Recheck late native faults and log replacement.
        return dict(self.evidence)

    def close(self, *, native_stopped):
        if native_stopped is not True:
            raise RuntimeError('native_fence_required_before_playback_cleanup')
        self.abort.set()
        self.release.set()
        if self.thread is not None:
            self.thread.join(6)
            if self.thread.is_alive():
                raise RuntimeError('native_playback_worker_not_joined')
        self.sock.close()
        self.evidence['worker_joined'] = True
        self.poll()
        self.installation.redact()
