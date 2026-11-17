"""Independent authenticated staging; no X4 launch, load claim or admission.

The async parent owns TLS bridges; an owned subprocess exclusively owns the
synchronous client. The caller keeps the output directory's parent exclusive.
"""
import asyncio
import json
import math
from pathlib import Path
import re
import socket
import sys
import time

# Also permit the private worker to run by absolute filename, independent of cwd.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from authority.experimental_client_owner import ExperimentalClientOwner
from authority.experimental_tls_tunnel import start_client

MAX_CONFIG = 16384
MAX_RESULT = 4096


class ClientStageError(RuntimeError):
    """Only fixed, credential-free failure categories cross the process boundary."""


def _listener():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(('127.0.0.1', 0))
        listener.listen(4)
        return listener
    except BaseException:
        listener.close()
        raise


def _validate_result(raw):
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ClientStageError('invalid_worker_result') from None
    if (type(result) is not dict or set(result) !=
            {'version', 'status', 'sha256', 'size', 'checkpoint_id', 'admitted'} or
            type(result['version']) is not int or result['version'] != 1 or
            result['status'] != 'staged' or result['admitted'] is not False or
            type(result['sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}', result['sha256']) or
            type(result['size']) is not int or result['size'] < 0 or
            type(result['checkpoint_id']) is not str or
            not re.fullmatch(r'checkpoint-[0-9a-f]{32}', result['checkpoint_id'])):
        raise ClientStageError('invalid_worker_result')
    return result


async def _read_result(stream):
    output = bytearray()
    while True:
        chunk = await stream.read(MAX_RESULT+1-len(output))
        if not chunk:
            return bytes(output)
        output.extend(chunk)
        if len(output) > MAX_RESULT:
            raise ClientStageError('worker_result_too_large')


async def _discard_output(stream):
    # Drain during termination so a full stdout pipe cannot hold Process.wait.
    while await stream.read(65536):
        pass


async def _reap(process):
    drain = asyncio.create_task(_discard_output(process.stdout))
    try:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(process.wait(), 2)
        except TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                raise ClientStageError('worker_reap_failed') from None
    finally:
        drain.cancel()
        await asyncio.gather(drain, return_exceptions=True)


async def _cleanup(spawn_task, tunnel, listeners):
    failures = []
    if spawn_task is not None:
        try:
            process = await spawn_task
        except BaseException:
            process = None  # A failed spawn returned no owned process.
        if process is not None:
            try:
                await _reap(process)
            except BaseException:
                failures.append('worker_cleanup_failed')
    if tunnel is not None:
        try:
            await asyncio.wait_for(tunnel.close(), 5)
        except BaseException:
            failures.append('tunnel_cleanup_failed')
    for listener in listeners:
        listener.close()
    return failures


async def stage_client_connection(*, server_host, server_port, server_fingerprint,
                                  shared_key, file_token, file_slot, new_directory,
                                  deadline, io_timeout=30, keepalive_interval=None):
    """Stage one offered save through pinned TLS, then disconnect without claiming.

    deadline is an absolute parent monotonic time, at most one hour ahead.
    On cancellation cleanup is awaited, even under repeated cancellation.
    TERM/kill waits are bounded; failure to reap is reported, not hidden.
    Failed attempts can leave partial or verified files for caller inspection.
    """
    if (type(deadline) not in (int, float) or not math.isfinite(deadline) or
            not 0 < deadline-time.monotonic() <= 3600 or
            type(file_token) is not str or not re.fullmatch(r'[0-9a-f]{32}', file_token) or
            type(file_slot) is not int or not 1 <= file_slot <= 8 or
            type(io_timeout) not in (int, float) or not math.isfinite(io_timeout) or not 0 < io_timeout <= 300 or
            (keepalive_interval is not None and (type(keepalive_interval) not in (int, float) or
             not math.isfinite(keepalive_interval) or not 0 < keepalive_interval <= 300))):
        raise ValueError('invalid_staging_options')
    destination = Path(new_directory).absolute()
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise ValueError('new_directory_required')
    listeners, tunnel, spawn_task, original_error = [], None, None, None
    try:
        async with asyncio.timeout(max(0, deadline-time.monotonic())):
            listeners.append(_listener())
            listeners.append(_listener())
            control_port, file_port = [listener.getsockname()[1] for listener in listeners]
            tunnel = await start_client(control_listener=listeners[0], file_listener=listeners[1],
                server_host=server_host, server_port=server_port, server_fingerprint=server_fingerprint,
                shared_key=shared_key, max_connections=2)
            config = dict(control_port=control_port, file_port=file_port, file_token=file_token,
                file_slot=file_slot, new_directory=str(destination), remaining_seconds=deadline-time.monotonic(),
                io_timeout=io_timeout, keepalive_interval=keepalive_interval)
            encoded = json.dumps(config, allow_nan=False).encode('utf-8')
            if len(encoded) > MAX_CONFIG:
                raise ValueError('configuration_too_large')
            spawn_task = asyncio.create_task(asyncio.create_subprocess_exec(
                sys.executable, str(Path(__file__).resolve()), '--worker',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL))
            process = await asyncio.shield(spawn_task)
            process.stdin.write(encoded)
            await process.stdin.drain()
            process.stdin.close()
            raw = await _read_result(process.stdout)
            returncode = await process.wait()
            if returncode != 0:
                raise ClientStageError('staging_failed')
            return _validate_result(raw)
    except BaseException as error:
        original_error = error
        raise
    finally:
        cleanup_task = asyncio.create_task(_cleanup(spawn_task, tunnel, listeners))
        cancellation = None
        while True:
            try:
                failures = await asyncio.shield(cleanup_task)
                break
            except asyncio.CancelledError as error:
                cancellation = error
        if cancellation is not None:
            for failure in failures:
                cancellation.add_note(failure)
            raise cancellation
        if failures:
            if original_error is not None:
                for failure in failures:
                    original_error.add_note(failure)
            else:
                raise ClientStageError('cleanup_failed')


def _stage_worker():
    connection = owner = None
    try:
        raw = sys.stdin.buffer.read(MAX_CONFIG+1)
        if len(raw) > MAX_CONFIG:
            raise ValueError('configuration_too_large')
        config = json.loads(raw)
        if type(config) is not dict or set(config) != {'control_port', 'file_port', 'file_token',
                'file_slot', 'new_directory', 'remaining_seconds', 'io_timeout', 'keepalive_interval'}:
            raise ValueError('invalid_configuration')
        remaining = config['remaining_seconds']
        if type(remaining) not in (int, float) or not math.isfinite(remaining) or not 0 < remaining <= 3600:
            raise ValueError('invalid_deadline')
        deadline = time.monotonic()+remaining
        connection = socket.create_connection(('127.0.0.1', config['control_port']),
            timeout=min(config['io_timeout'], remaining))
        owner = ExperimentalClientOwner(connection, enabled=True, file_host='127.0.0.1',
            file_port=config['file_port'], file_token=config['file_token'], file_slot=config['file_slot'],
            deadline=deadline, io_timeout=config['io_timeout'], keepalive_interval=config['keepalive_interval'])
        bound = owner.request_offer()
        path = owner.download(Path(config['new_directory']))
        owner.verify_staged(path)
        result = dict(version=1, status='staged', sha256=bound.offer.sha256,
            size=bound.offer.size, checkpoint_id=bound.offer.checkpoint_id, admitted=False)
    except BaseException:
        result = {'version': 1, 'status': 'failed'}
    finally:
        try:
            if owner is not None:
                owner.close()
            elif connection is not None:
                connection.close()
        except BaseException:
            result = {'version': 1, 'status': 'failed'}
    sys.stdout.write(json.dumps(result, separators=(',', ':'))+'\n')
    return 0 if result['status'] == 'staged' else 1


if __name__ == '__main__':
    raise SystemExit(_stage_worker() if sys.argv[1:] == ['--worker'] else 2)
