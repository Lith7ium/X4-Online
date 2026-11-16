# Local UDP module selection experiment

The opt-in participant/job diagnostic selects the bundled native Lua module
from `ffi.os`: `x4lan_net.so` on Linux and `x4lan_net_64.dll` on Windows. Other
platforms fail closed. The loader calls `package.loadlib` only when the session
starts; importing it does not load native code or open a socket. A missing or
invalid module fails the session; it does not fall back to another platform.

`src/native/build.py` can cross-build both filenames. The existing diagnostic
installer and its process/peer checks are Linux-specific and still install only
the Linux module. This change does not provide a Windows installer, peer
identity verification, connected Windows helper, or Windows X4 runtime proof.
In particular, it must not be used as justification to disable Linux peer
guards. Selection tests simulate both platform names in Linux LuaJIT; they do
not load a Windows DLL or demonstrate X4 gameplay or an Internet session.
