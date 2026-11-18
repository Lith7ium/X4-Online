#!/usr/bin/env python3
"""Opt-in, no-game Windows x64 Lua/network DLL loopback diagnostic.

Loads the caller's hash-pinned installed Lua DLL read-only, then loads the
project network DLL through real Lua package.loadlib. No game/profile/save
access, downloads, child processes or helper threads. An outer process timeout
is still required by the caller for a native crash/hang inside a DLL.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import struct
import time


def checked_dll(value: str, expected: str) -> tuple[Path, str]:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('DLL paths must be absolute')
    path = path.resolve(strict=True)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if len(expected) != 64 or digest != expected.lower():
        raise ValueError(f'SHA-256 mismatch: {path}')
    if data[:2] != b'MZ' or len(data) < 64:
        raise ValueError(f'Not a PE DLL: {path}')
    pe = struct.unpack_from('<I', data, 60)[0]
    if (data[pe:pe + 4] != b'PE\0\0'
            or struct.unpack_from('<H', data, pe + 4)[0] != 0x8664
            or struct.unpack_from('<H', data, pe + 24)[0] != 0x20b
            or not struct.unpack_from('<H', data, pe + 22)[0] & 0x2000):
        raise ValueError(f'Expected Windows x64 PE32+ DLL: {path}')
    return path, digest


class Lua:
    def __init__(self, path: Path):
        # C ABI prototypes: src/native/engine/linux/test_gate_engine.c:36-42;
        # luaL_loadstring(lua_State*, const char*) also checked against local
        # toolchain lauxlib.h and installed lua51_64.dll's actual export table.
        self.dll = ctypes.CDLL(str(path))
        signatures = {
            'luaL_newstate': (ctypes.c_void_p, []),
            'luaL_openlibs': (None, [ctypes.c_void_p]),
            'luaL_loadstring': (ctypes.c_int, [ctypes.c_void_p, ctypes.c_char_p]),
            'lua_pcall': (ctypes.c_int, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]),
            'lua_tolstring': (ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]),
            'lua_settop': (None, [ctypes.c_void_p, ctypes.c_int]),
            'lua_close': (None, [ctypes.c_void_p]),
        }
        for name, (result, args) in signatures.items():
            function = getattr(self.dll, name)
            function.restype, function.argtypes = result, args
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel.GetModuleHandleW.restype = ctypes.c_void_p
        if kernel.GetModuleHandleW('lua51_64.dll') != self.dll._handle:
            raise RuntimeError('Network module would resolve a different Lua runtime')
        self.state = self.dll.luaL_newstate()
        if not self.state:
            raise RuntimeError('luaL_newstate failed')
        self.dll.luaL_openlibs(self.state)

    def run(self, script: str) -> str:
        status = self.dll.luaL_loadstring(self.state, script.encode('utf-8'))
        if not status:
            status = self.dll.lua_pcall(self.state, 0, 1, 0)
        length = ctypes.c_size_t()
        pointer = self.dll.lua_tolstring(self.state, -1, ctypes.byref(length))
        result = ctypes.string_at(pointer, length.value).decode('utf-8', errors='replace') if pointer else ''
        self.dll.lua_settop(self.state, 0)
        if status:
            raise RuntimeError(f'Lua error {status}: {result}')
        return result

    def close(self):
        if self.state:
            self.dll.lua_close(self.state)
            self.state = None


def lua_string(value: str) -> str:
    # Lua 5.1 decimal byte escapes avoid JSON/Lua escape incompatibilities.
    return '"' + ''.join('\\%03d' % byte for byte in value.encode('utf-8')) + '"'


def probe(args, report: dict) -> None:
    if os.name != 'nt' or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError('Requires Windows x64 Python (Wine must be labelled explicitly)')
    ntdll = ctypes.WinDLL('ntdll')
    under_wine = hasattr(ntdll, 'wine_get_version')
    report['wine_detected'] = under_wine
    if under_wine != (args.runtime_environment == 'wine'):
        raise RuntimeError('Declared runtime environment disagrees with Wine export detection')
    runtime, runtime_sha = checked_dll(args.lua_dll, args.lua_sha256)
    network, network_sha = checked_dll(args.network_dll, args.network_sha256)
    if runtime.name.lower() != 'lua51_64.dll':
        raise ValueError('Runtime DLL basename must be lua51_64.dll')
    report['inputs'] = {'lua_dll': str(runtime), 'lua_sha256': runtime_sha,
                        'network_dll': str(network), 'network_sha256': network_sha}
    lua = Lua(runtime)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
            peer.bind(('127.0.0.1', 0))
            peer.settimeout(2)
            port = peer.getsockname()[1]
            version = lua.run(f'''
assert(_VERSION == 'Lua 5.1', 'Expected Lua 5.1 ABI')
local loader, err = package.loadlib({lua_string(str(network))}, 'luaopen_x4lan_net')
assert(loader, err)
net = assert(loader())
assert(type(net) == 'table')
conn = assert(net.open('127.0.0.1', {port}))
assert(conn:pending() == false)
assert(conn:receive() == nil)
assert(conn:send(string.rep('x', 769)) == false)
assert(conn:send('windows-network-smoke'))
first_clock = assert(net.monotonic())
assert(type(first_clock) == 'number' and first_clock >= 0)
return _VERSION .. ';' .. (jit and jit.version or 'no-jit-global')
''')
            report['checks'].append('real_package_loadlib')
            report['lua_version'] = version
            message, address = peer.recvfrom(2048)
            if message != b'windows-network-smoke' or address[0] != '127.0.0.1':
                raise RuntimeError('Unexpected loopback handshake')
            report['checks'].extend(['empty_initial_socket', 'oversized_send_rejected', 'loopback_udp_send'])
            # Reuse authority_net_pending.lua's zero/oversize/ordinary sequence,
            # but coordinate in Python without requiring FFI usleep or threads.
            for label, payload in [('empty', b''), ('oversized', b'x' * 1000), ('echo', message)]:
                peer.sendto(payload, address)
                deadline = time.monotonic() + 2
                while lua.run('return tostring(conn:pending())') == 'false':
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f'UDP readiness timed out: {label}')
                    time.sleep(0.001)
                expected = 'nil' if label != 'echo' else lua_string(message.decode())
                lua.run(f'''
assert(conn:pending() == true)
assert(conn:receive() == {expected})
assert(conn:pending() == false)
return 'ok'
''')
                report['checks'].append('pending_receive_' + label)
            time.sleep(0.02)
            delta = float(lua.run('''
local now = assert(net.monotonic())
assert(now >= first_clock)
return string.format('%.9f', now - first_clock)
'''))
            if not math.isfinite(delta) or delta <= 0:
                raise RuntimeError('Monotonic clock did not advance')
            report['monotonic_elapsed_seconds'] = delta
            report['checks'].append('monotonic_advanced')
            lua.run('''
conn:close(); conn:close()
assert(conn:pending() == nil)
assert(conn:receive() == nil)
assert(conn:send('closed') == false)
return 'ok'
''')
            report['checks'].append('closed_socket_and_idempotent_close')
    finally:
        lua.close()
    report['checks'].append('lua_state_closed')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic-windows-network', action='store_true', required=True)
    parser.add_argument('--runtime-environment', choices=('wine', 'native-windows'), required=True)
    parser.add_argument('--lua-dll', required=True)
    parser.add_argument('--lua-sha256', required=True)
    parser.add_argument('--network-dll', required=True)
    parser.add_argument('--network-sha256', required=True)
    args = parser.parse_args()
    report = {
        'diagnostic': 'windows_x64_network_dll_loopback',
        'passed': False, 'checks': [],
        'runtime_environment_declared_by_caller': args.runtime_environment,
        'native_windows_network_smoke_passed': False,
        'boundary': 'No X4 process, game UI, profiles, saves, multiplayer or cross-platform gameplay tested.',
    }
    try:
        probe(args, report)
        report['passed'] = True
        report['native_windows_network_smoke_passed'] = args.runtime_environment == 'native-windows'
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    print(json.dumps(report, sort_keys=True), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
