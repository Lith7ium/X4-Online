# Saved-registry job observer attach experiment

This is an opt-in diagnostic for one isolated Linux X4 process. It reads the
pinned, confirmed census checkpoint with its saved marker and 10,054-entry
registry; it does not rerun the census or modify the source archive. The
provenance verifier checks the archived save bytes, marker, registry epoch and
saved forward/reverse mapping. The archive and the fresh output must be
disjoint, including the whole original experiment directory.

Only the previously saved marker, registry and identity fixture MD scripts,
plus the new job queue, are installed. The archived scripts are byte-checked.
A single load UI update owner observes the load marker and pause, then starts
one serialized registry consumer. While paused, the consumer checks the saved
registry epoch and count, requires the queue to report uninitialized, and
initializes it once. Only `attached_wait_running` emits READY; a subsequent
update requests resume. The saved registry epoch and random load-attempt epoch
are distinct. After a bounded observation and queue drain, the owner pauses
again. The private save directory is bound read-only in the X4 namespace;
autosave is disabled and no save command is issued.

The underlying archive harness gates the owned process, fences signals, checks
Steam identity and protected files, verifies log continuity and final evidence,
and retains the lock if owned-process shutdown cannot be confirmed. A failure
invalidates the entire attempt; discard the private instance rather than retry
its potentially mutated in-memory registry or queue. The original checkpoint
remains the source for any future independent run.

`previously_unobserved_existing_index` is an existing index not previously
seen by this consumer. `new_registry_entry` is a first registry allocation;
neither proves that a ship was newly built. Queue ACK is local processing, not
network delivery. Events before queue initialization are absent, and job
activations are not all ship creation sources. Zero events are inconclusive.
Events may also arrive between the final empty queue observation and the
confirmed pause, so that observation is not a complete end-of-window census.
Even a successful run does not prove exact X4 file consumption, no game advance
before the first pause, complete universe coverage, client creation, Windows,
Internet connectivity, or multiplayer gameplay. This does not establish general
MD queue freshness or resume behaviour beyond the bounded run below. No normal
profile or saves are used.

## Native observation: `authority-job-attach-01`

One isolated Linux X4 run requested `save_009` and logged the expected
marker and pause, then READY with the stored registry epoch and baseline 10,054
before RESUMED. In a configured 60-second observation it reported 23 sequential
local events and ACKs, all classified as first registry allocations, indices
10,055 through 10,077. The summary and final pause were logged in order; the
result reports no owned processes remaining. All 23 event records agree with
the engine log. This does not establish that the corresponding ships were newly
built or delivered to a client.

The confirmed source pointer and staged save SHA-256 agree with the pinned
checkpoint; the three saved MD scripts agree byte-for-byte with the archive
and the code used in the private overlay. The private save directory contains
only the staged slot after the run. The engine log contains no identified
probe, MD or Lua script fault; it does contain failed writes to the protected
`config.xml` and graphics/signature messages. The evidence remains sampled and
does not prove exact file consumption or uninterrupted pause. The in-memory
registry changes were discarded with the disposable process.
