# Private diagnostic file guard

`PinnedFileGuard` is a standalone, opt-in building block. It is not connected
to the current diagnostic or its safety guards.

The caller supplies an absolute path and an independently obtained SHA-256. The
helper opens a regular file read-only without following a final symlink and
compares the descriptor and path identity and metadata. `check()` repeats only
those comparisons; it does not read or hash contents. `verify_digest()` hashes
the pinned descriptor and checks metadata around the read. Its optional callback
must return `True` and can enforce deadlines and cheap process/session checks
between blocks. The caller must close the guard, preferably with `with`.
The callback must not reenter or alter the guard; detected reentry invalidates
it even if the callback catches the exception. Before closing, the helper
checks that the descriptor still refers to the pinned device and inode; if it
cannot establish that, it reports failure and does not close the descriptor.
Any failed started check or digest permanently invalidates that guard, including
callback aborts and digest mismatches; closing still performs the descriptor
identity check. Argument validation errors before a digest starts are exempt.

The intended future use is limited to isolated tests that already own the
relevant lifecycle, keep competing writers out, and use read-only binds for
the diagnostic processes. A read-only bind alone does not prevent an external
writer or another hard link from changing the underlying file. The caller must
run and check a full digest at each agreed synchronous probe boundary; file,
process, session and socket checks remain separately necessary. A new or
replacement checkpoint requires a new guard and verified expected digest.
The caller must also have exclusive control of this process's descriptor table
for the guard's lifetime. The descriptor check and `close` are not atomic, and
device/inode cannot distinguish an independent open of the same file: replacing
or closing the descriptor behind the guard violates this contract. A refused
cleanup must be reported and resolved by the descriptor-table owner.
All guard operations must run on one owner thread, or be externally serialized
for their entire duration. The reentry flag is not thread synchronization.

Metadata checks do not prove content remained unchanged between hashes. Even
matching boundary hashes cannot rule out a change followed by restoration in
between. Nor do they establish which bytes X4 actually loaded. An unexpected
metadata change, read failure, callback failure or digest mismatch invalidates
the probe. This is a weaker temporal claim than hashing at every guard call;
adopting it requires an explicit review of the test's safety contract.
