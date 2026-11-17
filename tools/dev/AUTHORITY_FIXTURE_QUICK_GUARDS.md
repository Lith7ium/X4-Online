# Private fixture observation guards

`--fixture-player-source-quick-guards` is an explicit opt-in for the isolated,
two-client Linux fixture player-source diagnostic. The normal strict mode is
unchanged. Admission and finalization still use the existing full digests. Only
within the bounded player observation do the frequent guards replace hashing
the three staged saves with pinned file-identity and metadata checks. Protected
configuration files, process and Steam identities, logs, participant admission,
seat, sockets and reader ownership continue to be checked as before.

All three saves are SHA-256 checked at observation entry and exit and before
and after each successful synchronous player pull. If a pull or its subsequent
boundary fails, the host is fenced and its non-secret progress records an
unconfirmed post-pull boundary; no successful test result is issued. A post
boundary is not attempted after a failed pull in an uncertain host state.
The result records metadata-check and
digest-check counts, bytes from successfully verified digest reads and elapsed
digest/observation time. These metrics cover this observation only; they are
not a measurement of total process reads or physical disk IO.

The private test supervisor must exclusively own the FD table and serialize
these guards on its owner thread. It must also own all writers, with no external
process modifying the files or their hard links. The X4 processes receive the
staged saves through read-only binds, but those binds cannot prevent a different
host process from writing to the underlying inode. Exclusive control of other
same-user processes cannot be proven by this mechanism and is an explicit test
assumption. Do not use this mode when that assumption does not hold.

Metadata checks and matching boundary digests do not prove the bytes stayed
unchanged between boundaries: a change followed by restoration can be missed.
They also do not prove which bytes X4 actually loaded. This is weaker temporal
evidence than the normal strict mode. The result records these limitations.
