#!/usr/bin/env python3
"""Stage an offered checkpoint through authenticated TLS; never load or claim it."""
import argparse
import asyncio
import json
import re
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src'))
from authority.experimental_client_connection import stage_client_connection


def _read_secret_file(path, width):
    with path.open('rb') as stream:
        raw = stream.read(width+3)  # Complete valid content plus one overflow byte.
    if not re.fullmatch(rb'[0-9a-f]{'+str(width).encode('ascii')+rb'}(?:\r?\n)?', raw):
        raise ValueError('invalid_secret_file')
    return raw.rstrip(b'\r\n').decode('ascii')


def _cleanup_failed(error):
    return (isinstance(error, RuntimeError) and error.args == ('cleanup_failed',)) or any(
        note in {'worker_cleanup_failed', 'tunnel_cleanup_failed'}
        for note in getattr(error, '__notes__', ()))


async def _run_stage(**options):
    try:
        return await stage_client_connection(**options)
    except asyncio.CancelledError as error:
        # Preserve cleanup failure before asyncio.run translates Ctrl-C to KeyboardInterrupt.
        if _cleanup_failed(error):
            raise RuntimeError('cleanup_failed') from None
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--fingerprint', required=True)
    parser.add_argument('--shared-key-file', required=True, type=Path, help='64 lowercase hexadecimal characters')
    parser.add_argument('--file-token-file', required=True, type=Path, help='32 hexadecimal characters')
    parser.add_argument('--slot', required=True, type=int)
    parser.add_argument('--out', required=True, type=Path, help='new directory; parent must exist and remain exclusive')
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--keepalive-interval', type=float)
    arguments = parser.parse_args()
    try:
        shared_key = bytes.fromhex(_read_secret_file(arguments.shared_key_file, 64))
        file_token = _read_secret_file(arguments.file_token_file, 32)
        result = asyncio.run(_run_stage(server_host=arguments.host, server_port=arguments.port,
            server_fingerprint=arguments.fingerprint, shared_key=shared_key, file_token=file_token,
            file_slot=arguments.slot, new_directory=arguments.out,
            deadline=time.monotonic()+arguments.timeout, keepalive_interval=arguments.keepalive_interval))
    except KeyboardInterrupt:
        print(json.dumps({'status': 'failed', 'error_class': 'cancelled'}))
        return 1
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_class': 'cleanup_failed' if _cleanup_failed(error) else 'staging_failed'}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
