"""Pumpable, loopback-only experiment for cooperative participant control.

The caller owns this connected socket after consuming the load-accepted frame,
the X4 process and the injected synchronous controller. A controller result is
a local assertion; this module does not establish process or peer identity.
"""
import copy
import json
import math
import re
import select
import socket
import threading
import time

from .load_messages import MAX_INTEGER, MAX_MESSAGE, _pairs, _reject_constant
from .experimental_tcp_job_delivery import job_event, job_digest


class ExperimentalTCPParticipantClient:
    """Accept one command at a time, and reply only after local confirmation.

    The controller must bound its own synchronous pause/resume calls. This
    adapter checks its deadline after a call but cannot interrupt that call.
    """
    def __init__(self, conn, controller, *, enabled=False, epoch, handle, timeout=30, apply_job=None, apply_motion=None, apply_motion_once=None):
        if (enabled is not True or type(conn) is not socket.socket or conn.family != socket.AF_INET or
                conn.proto not in (0, socket.IPPROTO_TCP) or
                conn.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM or
                type(epoch) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', epoch) or
                type(handle) is not int or not 1 <= handle <= MAX_INTEGER or
                type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300 or
                not callable(getattr(controller, 'pause', None)) or
                not callable(getattr(controller, 'resume', None))):
            raise ValueError('enabled client, controller and bounded configuration required')
        if conn.getpeername()[0] != '127.0.0.1':
            raise ValueError('experimental client requires loopback peer')
        conn.setblocking(False)
        self._conn, self._controller, self._epoch, self._handle = conn, controller, epoch, handle
        self._timeout = float(timeout)
        self._thread = threading.get_ident()
        self._in = self._out = b''
        self._deadline = None
        self._last = 0
        if apply_job is not None and not callable(apply_job):
            raise ValueError('job application must be callable')
        if apply_motion is not None and not callable(apply_motion):
            raise ValueError('motion consumer must be callable')
        if apply_motion_once is not None and not callable(apply_motion_once):
            raise ValueError('one-shot motion writer must be callable')
        self._apply_job=apply_job;self._job_incarnation=None;self._last_job=None
        self._apply_motion=apply_motion;self._motion_incarnation=None;self._motion_tracks={};self._motion_current={}
        self._apply_motion_once=apply_motion_once;self._motion_write_attempted=False
        self._failed = self._closed = self._busy = False

    def _fault(self):
        self._failed = True
        try: self._conn.close()
        except BaseException: pass

    def _owner(self):
        if threading.get_ident() != self._thread:
            raise RuntimeError('exclusive owner thread required')
        if self._failed or self._closed:
            raise RuntimeError('participant client unavailable; fence local controller')
        if self._busy:
            self._fault()
            raise RuntimeError('reentrant participant client access')

    def _within(self):
        if self._failed or self._closed:
            raise RuntimeError('participant client changed during operation')
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise TimeoutError('participant operation deadline exceeded')

    def _quiet(self):
        readable, _, exceptional = select.select([self._conn], [], [self._conn], 0)
        if readable or exceptional:
            raise RuntimeError('unexpected input or disconnect during participant operation')
        self._within()

    def _command(self, raw):
        try:
            command = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_reject_constant)
        except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError('invalid participant command') from error
        if type(command) is dict and command.get('kind')=='job_delivery':
            return self._job(command)
        if type(command) is dict and command.get('kind') in ('motion_snapshot','motion_despawn'):
            return self._motion(command)
        if type(command) is dict and command.get('kind')=='motion_apply':
            return self._motion_apply(command)
        fields = {'version', 'kind', 'epoch', 'connection_handle', 'request_id', 'operation'}
        if (type(command) is not dict or set(command) != fields or
                type(command['version']) is not int or command['version'] != 1 or
                command['kind'] != 'participant_command' or command['epoch'] != self._epoch or
                type(command['connection_handle']) is not int or command['connection_handle'] != self._handle or
                type(command['request_id']) is not int or not self._last < command['request_id'] <= MAX_INTEGER or
                command['operation'] not in ('pause', 'resume')):
            raise ValueError('unexpected or stale participant command')
        self._quiet()
        self._last = command['request_id']  # never dispatch it twice
        confirmed = getattr(self._controller, command['operation'])((self._handle,))
        self._within()
        self._quiet()
        if confirmed is not True:
            raise RuntimeError('local participant state not confirmed')
        reply = dict(command, kind='participant_receipt', status='confirmed')
        self._out = json.dumps(reply, sort_keys=True, separators=(',', ':')).encode('utf-8') + b'\n'

    def _job(self, command):
        fields={'version','kind','connection_handle','request_id','session_epoch','incarnation','event'}
        if (self._apply_job is None or set(command)!=fields or type(command.get('version')) is not int or
                command['version']!=1 or type(command.get('connection_handle')) is not int or
                command['connection_handle']!=self._handle or command.get('session_epoch')!=self._epoch or
                type(command.get('request_id')) is not int or type(command.get('incarnation')) is not str or
                not re.fullmatch(r'[0-9a-f]{32}',command['incarnation'])):
            raise ValueError('invalid job command')
        event=job_event(command['event'])
        if (command['request_id']!=event['sequence'] or
                self._motion_incarnation is not None and self._motion_incarnation!=command['incarnation'] or
                self._job_incarnation is not None and self._job_incarnation!=command['incarnation'] or
                self._last_job is not None and (event['epoch'],event['generation'])!=self._last_job[:2] or
                self._last_job is not None and event['sequence']!=self._last_job[2]+1):
            raise ValueError('stale job command')
        self._quiet()
        self._job_incarnation=command['incarnation']
        self._last_job=(event['epoch'],event['generation'],event['sequence'])
        digest=job_digest(event)
        applied=copy.deepcopy(event)
        confirmed=self._apply_job(applied)
        self._within();self._quiet()
        if job_digest(applied)!=digest:raise ValueError('job application mutated its event')
        if confirmed is not True:raise RuntimeError('local job application not confirmed')
        reply={k:command[k] for k in ('version','connection_handle','request_id','session_epoch','incarnation')}
        reply.update(kind='job_receipt',status='applied',event_sha256=digest)
        self._out=json.dumps(reply,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()+b'\n'

    def _motion(self, command):
        # The callback must bind the portable identity to the local X4 actor;
        # this adapter itself cannot establish a game binding.
        from .experimental_tcp_motion import motion_value, motion_digest
        fields={'version','kind','connection_handle','session_epoch','incarnation','request_id','sample'}
        if (self._apply_motion is None or set(command)!=fields or type(command.get('version')) is not int or
            command['version']!=1 or type(command.get('connection_handle')) is not int or
            command['connection_handle']!=self._handle or command.get('session_epoch')!=self._epoch or
            type(command.get('incarnation')) is not str or not re.fullmatch(r'[0-9a-f]{32}',command['incarnation']) or
            self._motion_incarnation is not None and self._motion_incarnation!=command['incarnation'] or
            self._job_incarnation is not None and self._job_incarnation!=command['incarnation']):
            raise ValueError('invalid motion command')
        despawn=command['kind']=='motion_despawn'
        sample=motion_value(command['sample'],despawn=despawn)
        if type(command['request_id']) is not int or command['request_id']!=sample['sequence']:
            raise ValueError('motion request identity mismatch')
        key=(sample['epoch'],sample['generation'],sample['index'])
        prior=self._motion_tracks.get(key)
        if prior is None:
            if despawn or len(self._motion_tracks)>=100000:raise ValueError('unknown motion lifetime')
            current=self._motion_current.get((sample['epoch'],sample['index']))
            if current is not None and not self._motion_tracks[current]['closed']:
                raise ValueError('previous motion lifetime active')
        elif prior['closed'] or sample['sequence']<=prior['sequence']:
            raise ValueError('stale motion lifetime')
        if not despawn and prior:
            if sample['source_time']<=prior['time']:raise ValueError('non-monotone motion time')
            if sample['sector_macro']!=prior['frame'] and sample['velocity'] is not None:
                raise ValueError('frame transition requires unknown velocity')
        self._quiet();self._motion_incarnation=command['incarnation']
        digest=motion_digest(sample,despawn=despawn);candidate=copy.deepcopy(sample)
        confirmed=self._apply_motion(candidate,despawn)
        self._within();self._quiet()
        if motion_digest(candidate,despawn=despawn)!=digest:raise ValueError('motion callback mutated sample')
        if confirmed is not True:raise RuntimeError('motion sample not accepted')
        self._motion_tracks[key]={'sequence':sample['sequence'],'closed':despawn,
            'time':None if despawn else sample['source_time'],'frame':None if despawn else sample['sector_macro'],
            'digest':None if despawn else digest}
        self._motion_current[(sample['epoch'],sample['index'])]=key
        reply={k:command[k] for k in ('version','connection_handle','session_epoch','incarnation','request_id')}
        reply.update(kind='motion_receipt',status='accepted',sample_sha256=digest)
        self._out=json.dumps(reply,sort_keys=True,separators=(',', ':')).encode()+b'\n'

    def _motion_apply(self,command):
        from .experimental_tcp_motion import motion_value, motion_digest
        fields={'version','kind','connection_handle','session_epoch','incarnation','request_id','sample'}
        if (self._apply_motion_once is None or self._motion_write_attempted or set(command)!=fields or
            type(command.get('version')) is not int or command['version']!=1 or
            type(command.get('connection_handle')) is not int or command['connection_handle']!=self._handle or
            command.get('session_epoch')!=self._epoch or type(command.get('incarnation')) is not str or
            command['incarnation']!=self._motion_incarnation):raise ValueError('one-shot motion apply unavailable')
        sample=motion_value(command['sample']);key=(sample['epoch'],sample['generation'],sample['index'])
        prior=self._motion_tracks.get(key);digest=motion_digest(sample)
        if (type(command.get('request_id')) is not int or command['request_id']!=sample['sequence'] or
            prior is None or prior['closed'] or prior['sequence']!=sample['sequence'] or prior['digest']!=digest):
            raise ValueError('motion apply differs from last confirmed sample')
        self._quiet();self._motion_write_attempted=True;candidate=copy.deepcopy(sample)
        accepted=self._apply_motion_once(candidate)
        self._within();self._quiet()
        if motion_digest(candidate)!=digest or accepted is not True:raise RuntimeError('motion readback not confirmed')
        reply={k:command[k] for k in ('version','connection_handle','session_epoch','incarnation','request_id')}
        reply.update(kind='motion_applied_receipt',status='applied',sample_sha256=digest)
        self._out=json.dumps(reply,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()+b'\n'

    def poll(self, timeout=0):
        """Pump bounded I/O once; True means a receipt was sent to the socket."""
        self._owner()
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 <= timeout <= 1:
            raise ValueError('invalid poll timeout')
        self._busy = True
        try:
            self._within()
            wait = timeout if self._deadline is None else min(timeout, max(0, self._deadline-time.monotonic()))
            readable, writable, exceptional = select.select([self._conn], [self._conn] if self._out else [], [self._conn], wait)
            self._within()
            if exceptional: raise RuntimeError('participant socket exception')
            if readable:
                if self._out: raise RuntimeError('pipelined participant command')
                try: chunk = self._conn.recv(MAX_MESSAGE+1-len(self._in))
                except BlockingIOError: chunk = None
                if chunk == b'': raise RuntimeError('participant peer disconnected')
                if chunk:
                    if self._deadline is None: self._deadline = time.monotonic()+self._timeout
                    self._in += chunk
                    if b'\n' in self._in:
                        frame, tail = self._in.split(b'\n', 1)
                        if tail or len(frame) > MAX_MESSAGE: raise ValueError('invalid participant framing')
                        self._in = b''
                        self._command(frame)
                    elif len(self._in) > MAX_MESSAGE:
                        raise ValueError('participant command too large')
            if writable and self._out:
                try: count = self._conn.send(self._out)
                except BlockingIOError: return False
                if count <= 0: raise RuntimeError('participant receipt send failed')
                self._out = self._out[count:]
                self._within()
                if not self._out:
                    self._deadline = None
                    return True
            return False
        except BaseException:
            self._fault()
            raise
        finally:
            self._busy = False

    def close(self):
        self._owner()
        self._closed = True
        self._conn.close()
