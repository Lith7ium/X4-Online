# Windows network DLL runtime diagnostic

`authority_windows_network_smoke.py` runs the project's Windows x64 UDP DLL
inside a standalone Windows x64 Python process. It loads an existing trusted
`lua51_64.dll` read-only and exercises the real Lua 5.1 `package.loadlib` path.
It does not start X4 or Steam, access game profiles or saves, or download files.
The Python peer and the DLL communicate over IPv4 loopback; no external
network service is needed.

Use absolute Windows paths for both DLLs and independently verified SHA-256
hashes for their exact contents. The Lua DLL must come from a trusted local
installation, retain the basename `lua51_64.dll`, and export the Lua 5.1 API.
The network DLL must be the intended project build. Do not substitute hashes
merely to bypass an unexpected mismatch. The probe checks both hashes and
Windows x64 PE DLL headers before loading either input.

Example from an already prepared isolated Windows/Wine environment:

```powershell
& 'C:\diagnostics\runtime\python.exe' 'C:\diagnostics\authority_windows_network_smoke.py' `
  --diagnostic-windows-network `
  --runtime-environment wine `
  --lua-dll 'Z:\trusted\installed-game\lua51_64.dll' `
  --lua-sha256 '<verified Lua DLL SHA-256>' `
  --network-dll 'C:\diagnostics\x4lan_net_64.dll' `
  --network-sha256 '<verified project DLL SHA-256>'
```

Use `--runtime-environment native-windows` only on native Windows. The probe
checks the declaration against the presence of Wine's `wine_get_version`
export. It emits one JSON result on standard output and exits with code zero
when its network diagnostic passes (`passed: true`).
`native_windows_network_smoke_passed` stays false under Wine. Consult the
emitted scope fields and check list alongside the outer wrapper's result.

The caller must impose an outer process timeout and own the process it starts.
The probe's socket receive and polling waits are bounded, but a crash or hang
inside a native DLL cannot be bounded by those Python waits. Under Wine, use
a fresh private prefix and a wrapper that records and cleans up only its owned
processes. Prefix preparation, outer timeout, process ownership and cleanup
are separate checks; successful network assertions do not establish their
success.

The diagnostic covers real module loading, outbound UDP and loopback echo,
empty and oversized datagram readiness/receive behavior, rejected oversized
sends, an advancing monotonic clock, and repeated socket close behavior. Lua
state closure releases its remaining resources, including on ordinary errors.

A Wine result establishes behavior under that Wine runtime only. It does not
prove native Windows behavior, loading inside X4's UI, cross-platform gameplay,
Internet connectivity, or multiplayer acceptance. The first isolated Wine
execution exercised the network assertions successfully, but its outer wrapper
reported an incomplete prefix process scan; that execution must not be described
as an overall successful Wine run. No native Windows result is established by
that observation.
