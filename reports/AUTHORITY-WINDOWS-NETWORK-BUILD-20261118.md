# Windows fixture network module build

This is a cross-build and static inspection, not a Windows execution or X4
participant test. No game or Wine process was started.

## Why a separate build is needed

`src/authority/lua/local_udp_module.lua` requires the loaded native module to
provide both `open` and `monotonic`. The historical tracked DLL at
`src/lockstep/base/native/x4lan_net_64.dll` last changed at `6de08eed`; the source
at that revision registers only `open` on the module table. Static string
inspection of that DLL also found no `monotonic` registration name or
performance-counter import. Its SHA-256 is
`0fc98dba4d6844ffe2f59e0d827f73e5641b1c6aa5d71071641cabb4f80b6ab6`.
It is not suitable for the new fixture client. The legacy binary was left
unchanged; the new client accepts an explicitly supplied build and digest.

## Recorded build

Built at repository revision `d8bfeda3` using the existing `src/native/build.py`,
Zig 0.15.2, `--platform windows`, and a new output directory:
`.local/windows-fixture-network-20261118-01/`.

| Input/artifact | SHA-256 |
| --- | --- |
| `src/native/net.c` | `143185e4e0ef5e32aca4b000814b420ea71c374faa6dc3a193dcc3ca2e813191` |
| `src/native/build.py` | `a1b65d0484a1481bce09809346cd91d7cfa021f2d54c94988378eb0bb4c66059` |
| Built `x4lan_net_64.dll` | `6ad97e04fd804c031b673af7259e4010b0afb2ad095e8821647998a69e2809e0` |

The build completed successfully with `-Wall -Wextra -Werror`. `file` identified
a PE32+ x86-64 DLL; `objdump -p` found the `luaopen_x4lan_net` export and imports
of `QueryPerformanceCounter` and `QueryPerformanceFrequency`. The built file
contains the `monotonic` and `pending` registration names. These checks support
the intended binary target and API implementation, not successful DLL loading
or execution. The hash identifies this retained local artifact, not a promise
that every build environment produces identical bytes.

The Windows client guide now explicitly calls for a current-source build.
Native Windows still needs to establish that X4 loads the DLL, resolves its
loaded Lua runtime, and exchanges participant commands through it.
