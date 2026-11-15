# Experimental supplied-content comparison

`authority.content_compatibility.compare(host, client)` compares two explicitly
supplied Python dictionaries. It performs no file, registry, profile, Steam,
network or X4 access, and makes no admission decision. Return value is a frozen
`Comparison`: `equal` means the supported supplied fields match; `different`
reports the concrete disagreements; `unconfirmed` means at least one input is
missing, malformed, ambiguous or uses an unsupported schema/digest scheme.
Unconfirmed input takes precedence over apparent differences.

Schema 1 requires `game_version` and `game_build` as canonical nonnegative
decimal strings, `extensions` as an explicit list of active `{id, version}`
objects, and `scripts` as `{scheme, sha256}`. An explicit empty extensions list
is the producer's assertion that none are active; absence or `null` is unknown.
IDs are case-sensitive and must be unique. Only the reserved scheme label
`x4-authority-shared-scripts-v1` and lowercase SHA-256 syntax are accepted;
no collector or independent definition of what bytes that label covers is
implemented here. The producer must use the same documented byte selection
before these digests have any practical meaning. Unknown schemes are unconfirmed.

Optional `platform` (`linux` or `windows`) and `executable_sha256` are validated
for shape but excluded from comparison. Linux and Windows executables differ;
separate platform-specific installation/build validation is still required. An
equal manifest does not prove identical DLC assets, running-game extension
selection, source authenticity, trusted hash production, save compatibility,
X4 loading, or Windows/internet gameplay. Future collectors must distinguish
unavailable data from a confirmed empty list, and bind their findings to the
actual process and content selection. This module does not read existing
profiles or change Workshop or Steam settings.

`tests/test_authority_content_compatibility.py` exercises synthetic input only.
