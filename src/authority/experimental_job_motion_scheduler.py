"""Serialize a source-job bridge and a source-motion bridge on one TCP owner.

No process or socket is opened here. The caller owns the single thread, process
and profile fencing, and supplies already authenticated/owned local peers.
"""
import select
import threading
from .experimental_source_job_bridge import ExperimentalSourceJobBridge
from .experimental_source_motion_ipc import ExperimentalSourceMotionIPC
from .experimental_tcp_job_delivery import job_event

class ExperimentalJobMotionScheduler:
    """Prefer a queued job, otherwise pull one motion sample; never two readers."""
    def __init__(self,job,motion,*,enabled=False):
        if (enabled is not True or not isinstance(job,ExperimentalSourceJobBridge) or
            type(motion) is not ExperimentalSourceMotionIPC or job._delivery is not motion._motion._delivery or
            job._epoch!=motion._epoch or job._generation!=motion._generation or
            job._owner!=threading.get_ident() or motion._owner!=threading.get_ident() or
            job.state!='idle' or motion.state!='ready' or
            job._scheduler_owner is not None or motion._scheduler_owner is not None):
            raise ValueError('incompatible job/motion owner contexts')
        self._job=job;self._motion=motion;self._owner=threading.get_ident();self._state='ready';self._finished=False;self._job_barrier=False
        job._scheduler_owner=self;motion._scheduler_owner=self
    @property
    def state(self):return self._state
    def _fail(self):
        self._state='failed';self._motion._fail();self._job._state='failed'
        try:self._job._sock.close()
        except OSError:pass
    def _call(self,bridge,fn,*args,**kwargs):
        lease=object();bridge._scheduler_lease=lease
        try:return fn(*args,_scheduler=lease,**kwargs)
        finally:bridge._scheduler_lease=None
    def _fence_queued_job(self,control):
        if self._finished:return
        readable,_,bad=select.select([self._job._sock],[],[self._job._sock],0)
        if bad:raise RuntimeError('job source socket error')
        if readable:
            gate=control._latest_motion
            if self._job_barrier or not (gate.blocked or gate.world_blocked):
                self._job_barrier=True;control.motion_barrier()

    def step(self):
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('job/motion scheduler reentered or unavailable')
        self._state='working'
        try:
            control=self._motion._motion._delivery._host._control
            if self._motion._latest:
                # The existing host remains the sole TCP reader. One bounded
                # pump per step keeps all peers progressing while X4 replies.
                self._fence_queued_job(control)
                self._motion._motion._delivery._host.tick(0)
                if self._motion.state=='pulling':
                    done,sample=self._call(self._motion,self._motion.poll_latest)
                    self._fence_queued_job(control)
                    self._state='ready'
                    return ('motion',sample) if done else ('motion_pending',None)
                world=self._motion._motion._delivery._host._world.session
                if world.pending is not None or world.state!='running':
                    self._state='ready';return ('world_pending',None)
            if not self._finished:
                readable,_,bad=select.select([self._job._sock],[],[self._job._sock],0)
                if bad:raise RuntimeError('job source socket error')
                if readable:
                    if self._motion._latest:
                        gate=control._latest_motion
                        if not self._job_barrier and (gate.blocked or gate.world_blocked):
                            self._state='ready';return ('motion_fenced',None)
                        self._job_barrier=True
                        if not control.motion_barrier():
                            self._state='ready';return ('motion_drain',None)
                    result=self._call(self._job,self._job.run_one,allow_finished=True)
                    if result is None:
                        self._finished=True
                        if self._job_barrier:control.release_motion_barrier();self._job_barrier=False
                        self._state='ready';return ('job_snapshot_finished',None)
                    if type(result) is not dict or result.get('source_ack_observed') is not True:
                        raise RuntimeError('source job not acknowledged')
                    event=job_event(result['event'])
                    if event['epoch']!=self._motion._epoch or event['generation']!=self._motion._generation:
                        raise ValueError('job and motion lineage mismatch')
                    self._call(self._motion,self._motion.bind_confirmed,event['index'])
                    if self._job_barrier:control.release_motion_barrier();self._job_barrier=False
                    self._state='ready';return ('job',event)
            if self._motion._latest:
                if self._job_barrier:
                    self._state='ready';return ('motion_drain',None)
                started=self._call(self._motion,self._motion.begin_latest)
                self._state='ready';return ('motion_pending' if started else 'motion_fenced',None)
            sample=self._call(self._motion,self._motion.pull)
            self._state='ready';return ('motion',sample)
        except BaseException:
            self._fail();raise
    def _require_latest_barrier(self):
        if self._motion._latest:
            control=self._motion._motion._delivery._host._control
            if not control._latest_motion.blocked or not control._motion_idle():
                raise RuntimeError('drain explicit motion barrier before synchronous operation')

    def register_saved(self,index):
        """Request one explicitly fenced saved index on the same owner thread."""
        self._require_latest_barrier()
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('job/motion scheduler reentered or unavailable')
        self._state='working'
        try:
            self._require_quiet_job()
            result=self._call(self._motion,self._motion.register_saved,index)
            if result is not True:raise RuntimeError('saved registration unconfirmed')
            self._require_quiet_job()
            self._state='ready';return True
        except BaseException:
            self._fail();raise
    def _require_quiet_job(self):
        readable,_,bad=select.select([self._job._sock],[],[self._job._sock],0)
        if readable or bad:raise RuntimeError('unexpected source job during saved motion')
    def step_motion_only(self):
        """Diagnostic fence: do not consume, acknowledge or discard a source job.

        Point checks cannot exclude a producer event that is not yet queued.
        """
        if self._motion._latest:raise RuntimeError('use incremental step for latest motion')
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('job/motion scheduler reentered or unavailable')
        self._state='working'
        try:
            self._require_quiet_job()
            sample=self._call(self._motion,self._motion.pull)
            self._require_quiet_job()
            self._state='ready';return sample
        except BaseException:
            self._fail();raise
    def preflight(self,sample):
        """Run a read-only preflight without consuming a queued job."""
        self._require_latest_barrier()
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('job/motion scheduler reentered or unavailable')
        self._state='working'
        try:
            self._require_quiet_job();result=self._call(self._motion,self._motion.preflight,sample)
            if result not in ('near','ready'):raise RuntimeError('motion preflight unconfirmed')
            self._require_quiet_job();self._state='ready';return result
        except BaseException:
            self._fail();raise
    def apply_once(self,sample):
        """Apply one already-confirmed sample; failure may follow a side effect."""
        self._require_latest_barrier()
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('job/motion scheduler reentered or unavailable')
        self._state='working'
        try:
            self._require_quiet_job()
            if self._call(self._motion,self._motion.apply_once,sample) is not True:
                raise RuntimeError('motion write confirmation missing')
            self._require_quiet_job();self._state='ready';return True
        except BaseException:
            self._fail();raise
    def close(self):
        if self._state!='ready' or threading.get_ident()!=self._owner:
            self._fail();raise RuntimeError('job/motion scheduler cannot close')
        try:
            self._call(self._motion,self._motion.close);self._call(self._job,self._job.close);self._state='closed'
        except BaseException:
            self._fail();raise
