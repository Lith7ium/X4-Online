"""Bind the running client's opted-in read-only authority UDP endpoint.

Reuses the local correlation handshake but does not assert a paused source.
The caller must independently fence the running game, the test grant and the
actual PID/socket identity; this component does not authenticate the peer.
"""
from .experimental_source_job_binding import ExperimentalSourceJobBinding


class ExperimentalRunningClientAuthorityBinding(ExperimentalSourceJobBinding):
    """A separate enabled running-client context for HELLO/BOUND/ATTACHED.

    `guard`, `running` and `grant` are external, sampled assertions; their
    callbacks must independently establish the surrounding private session.
    No GO, pause, resume, game write or authority handover is sent.
    """
    def __init__(self,sock,*,enabled=False,lease,attempt,epoch,generation,guard,validate_peer,running,grant,timeout=30):
        if enabled is not True or not all(callable(f) for f in (guard,validate_peer,running,grant)):
            raise ValueError('enabled running-client binding and guards required')
        def context():
            return (guard() is True and running() is True and grant() is True and
                    guard() is True and running() is True and grant() is True and running() is True)
        super().__init__(sock,enabled=True,lease=lease,attempt=attempt,epoch=epoch,generation=generation,
                         guard=context,validate_peer=validate_peer,timeout=timeout)
