# Windows Documents known-folder lookup

The local pinned Windows X4 9.00 image at
`/var/home/bazzite/.local/share/Steam/ubuntu12_32/steamapps/content/app_392160/depot_392163/X4.exe`
is 55,412,768 bytes with SHA-256
`19750a6563889a970f434b5566eb396c6b2dc29ff814bd3e336f838176ad6891`.
Its PE imports `SHELL32!SHGetKnownFolderPath`. At RVA `0x14CA902`, the call
passes the GUID bytes for `FOLDERID_Documents`
(`FDD39AD0-238F-46AF-ADB4-6C85480369C7`), flags `0`, and a null token. The
returned path is then used to build a longer path. This was static inspection;
X4 was not run, and the remaining path construction was not traced to a final
profile path.

The launcher now asks Windows for the current user's Documents folder and
appends `Egosoft/X4`. This respects Known Folder redirection. The returned
string uses `CoTaskMemFree` on success and failure. Non-Windows path behavior
remains `USERPROFILE/Documents/Egosoft/X4`. Mocked ABI tests verify arguments,
Unicode paths, output cleanup, and failure handling; they do not validate a
live Windows installation.

References:

- [SHGetKnownFolderPath](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath)
- [Known Folder IDs](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid)
