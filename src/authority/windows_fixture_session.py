"""One opt-in Windows fixture join using caller-owned disposable resources.

This composes the existing experimental load, participant and process owners.
It does not prove loaded bytes, native Windows operation, gameplay or a WAN
session. The workspace owns the profile/view/log and must keep them exclusive.
"""
import math
import re
import time

from .experimental_client_session import client_connection
from .experimental_windows_fixture_overlay import install_fixture_overlay
from .load_observations import BoundReceiptStream
from .local_participant_control import LocalParticipantControl
from .observed_client_session import ObservedClientSession
from .windows_x4_process import WindowsX4Process


class FixtureCleanupError(RuntimeError):
    """An owned resource did not confirm cleanup; do not reuse the profile."""

    def __init__(self, message, *, process_owner, workspace):
        super().__init__(message)
        self.process_owner = process_owner
        self.workspace = workspace


def _annotate(error, message):
    try:
        error.add_note(message)
    except BaseException:
        pass


def run_fixture_session(*, enabled=False, workspace, server_host, server_port,
                        server_fingerprint, shared_key, file_token, file_slot,
                        windows_dll, dll_sha256, deadline, keepalive_interval,
                        stop_requested, io_timeout=30, participant_timeout=30):
    """Stage, admit and poll one fixture, stopping its owned job on every exit.

    The workspace must provide prepare/view/save_dir/download_dir/guard,
    register_overlay/read_log/redact_config/close. Its path, ACL, file and log
    assertions are caller responsibilities. No operation is automatically
    retried; cleanup cannot undo a possible claim or participant command.
    ``stop_requested`` is called only after admission. It and the workspace
    callbacks must be bounded and cannot be interrupted by the deadline. No
    profile is deleted or reused here.
    """
    if (enabled is not True or not callable(stop_requested) or
            type(deadline) not in (int, float) or not math.isfinite(deadline) or
            not 0 < deadline - time.monotonic() <= 3600 or
            type(keepalive_interval) not in (int, float) or not math.isfinite(keepalive_interval) or
            not 0 < keepalive_interval <= 300 or
            type(io_timeout) not in (int, float) or not math.isfinite(io_timeout) or not 0 < io_timeout <= 300 or
            type(participant_timeout) not in (int, float) or not math.isfinite(participant_timeout) or
            not 0 < participant_timeout <= 299 or
            type(server_host) is not str or not server_host or type(server_port) is not int or
            not 1 <= server_port <= 65535 or type(file_slot) is not int or not 1 <= file_slot <= 8 or
            type(server_fingerprint) is not str or not re.fullmatch(r'[0-9a-f]{64}', server_fingerprint) or
            type(shared_key) is not bytes or len(shared_key) != 32 or
            type(file_token) is not str or not re.fullmatch(r'[0-9a-f]{32}', file_token) or
            type(dll_sha256) is not str or not re.fullmatch(r'[0-9a-f]{64}', dll_sha256)):
        raise ValueError('invalid enabled fixture session configuration')

    outer_error = None
    try:
        workspace.prepare()
        with client_connection(server_host=server_host, server_port=server_port,
                server_fingerprint=server_fingerprint, shared_key=shared_key, file_token=file_token,
                file_slot=file_slot, deadline=deadline, io_timeout=io_timeout,
                keepalive_interval=keepalive_interval) as owner:
            controller = process = session = None
            launch_attempted = overlay_registered = False
            original = None
            cleanup_errors = []
            process_stopped = False
            result = None
            try:
                if time.monotonic() >= deadline or workspace.guard() is not True:
                    raise RuntimeError('fixture workspace unavailable')
                bound = owner.request_offer()
                download = owner.download(workspace.download_dir)
                owner.copy_to_new_slot(download, workspace.save_dir / 'save_009.xml.gz')
                controller = LocalParticipantControl(enabled=True, timeout=participant_timeout)
                hashes = install_fixture_overlay(workspace.view, new_test_view=True, bound_offer=bound,
                    save_path=str(workspace.save_dir), participant_port=controller.sock.getsockname()[1],
                    participant_lease=controller.lease, windows_dll=windows_dll, dll_sha256=dll_sha256)
                workspace.register_overlay(hashes)
                overlay_registered = True
                def launch_guard():
                    return time.monotonic() < deadline and workspace.guard() is True and time.monotonic() < deadline

                if launch_guard() is not True:
                    raise RuntimeError('fixture workspace changed before launch')
                process = WindowsX4Process(enabled=True)
                launch_attempted = True
                process.start(workspace.view, profile_id=45841, guard=launch_guard)

                def running_guard():
                    return (time.monotonic() < deadline and workspace.guard() is True and
                            process.is_running() is True and workspace.guard() is True and
                            time.monotonic() < deadline)

                session = ObservedClientSession(owner, bound, controller, slot='save_009',
                    read_log=workspace.read_log, guard=running_guard, deadline=deadline)
                if session.start() is not True:
                    raise RuntimeError('fixture admission unconfirmed')
                commands = 0
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('fixture session deadline expired')
                    if running_guard() is not True:
                        raise RuntimeError('fixture process or workspace changed')
                    stop = stop_requested()
                    if type(stop) is not bool:
                        raise ValueError('stop callback must return a boolean')
                    if time.monotonic() >= deadline:
                        raise TimeoutError('fixture session deadline expired')
                    if running_guard() is not True:
                        raise RuntimeError('fixture process or workspace changed')
                    if stop:
                        break
                    poll_started = time.monotonic()
                    if session.poll(.1):
                        commands += 1
                    now = time.monotonic()
                    if now >= deadline:
                        raise TimeoutError('fixture session deadline expired')
                    delay = min(.05 - (now - poll_started), deadline - now)
                    if delay > 0:
                        time.sleep(delay)
                result = {'client_admitted': True, 'participant_receipts': commands}
            except BaseException as error:
                original = error
            finally:
                if process is not None:
                    try:
                        closed = process.close()
                        process_stopped = closed is True and process.cleanup_confirmed is True
                        if launch_attempted and not process_stopped:
                            cleanup_errors.append('owned X4 stop unconfirmed')
                    except BaseException:
                        cleanup_errors.append('owned X4 cleanup failed')
                if process_stopped and result is not None and original is None:
                    try:
                        if workspace.guard() is not True:
                            raise RuntimeError('fixture workspace unavailable')
                        final_log = workspace.read_log()
                        if (type(final_log) is not bytes or len(final_log) > 8 << 20 or
                                not BoundReceiptStream(bound, slot='save_009').feed(final_log) or
                                workspace.guard() is not True):
                            raise RuntimeError('final fixture observations incomplete')
                    except BaseException:
                        cleanup_errors.append('final fixture observations unconfirmed')
                if session is not None:
                    try:
                        session.close()
                    except BaseException:
                        cleanup_errors.append('participant session cleanup failed')
                elif controller is not None:
                    try:
                        controller.close()
                    except BaseException:
                        cleanup_errors.append('participant controller cleanup failed')
                if overlay_registered and (not launch_attempted or process_stopped):
                    try:
                        workspace.redact_config()
                    except BaseException:
                        cleanup_errors.append('fixture configuration redaction failed')
            if cleanup_errors:
                failure = FixtureCleanupError('; '.join(cleanup_errors), process_owner=process, workspace=workspace)
                if original is not None:
                    _annotate(original, str(failure))
                    try:
                        original.fixture_cleanup = failure
                    except BaseException:
                        pass
                    raise original
                raise failure
            if original is not None:
                raise original
            result.update(owned_cleanup_confirmed=True, configuration_redacted=True)
            return result
    except BaseException as error:
        outer_error = error
        raise
    finally:
        try:
            workspace.close()
        except BaseException as cleanup_error:
            if outer_error is not None:
                _annotate(outer_error, 'fixture workspace cleanup failed: ' + type(cleanup_error).__name__)
            else:
                raise FixtureCleanupError('fixture workspace cleanup failed', process_owner=None,
                                          workspace=workspace) from cleanup_error
