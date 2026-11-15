# Marked local load: descriptive evidence only

`tools/dev/authority_marked_admission_evidence.py` is an isolated,
read-only evidence checker for development. It starts no X4 process, transfers
nothing and performs no admission. Its output must not be used to set
`trusted_confirmation`, unpause a session, or decide that a real client may
join. It does not establish a safe or runnable admission flow.

The checker compares a caller-supplied attempt and the coordinator's in-memory
load offer and session, initially checks the confirmed checkpoint, verifies its
saved marker, hashes the staged target using a no-follow file descriptor, and
examines local log observations for matching fixture identities and ordered
load, marker and pause receipts. The caller supplies process and protected-file
checks; returning `True` from such a callback is an assertion, not independent
authentication. The checker makes repeated point-in-time checks, but they are
not an atomic snapshot or a continuous guarantee. In particular, the confirmed
checkpoint pointer, manifest or save may change after the initial check and
before the result is returned. A matching marker does not prove which bytes X4
actually consumed; local logs and attempts are not authenticated. The result
explicitly states that checkpoint freshness at return and admission are not
proven.

The unit tests use synthetic logs and coordinator state, including a mocked
saved-marker verifier. They test rejection and the known checkpoint-freshness
limit, not native X4 behavior or the integrity of caller-supplied checks.

A proposed native runner and its base-harness patch are retained as a local
unreviewed draft under `.local/marked-admission-draft-01`; they are not part of
the active test or installation path. Before a native admission experiment,
separate work must establish and test at least:

- checkpoint pointer, manifest and save identity bound to the validated
  snapshot and fenced until admission;
- current process ownership, protected files and complete ordered logs checked
  at the actual admission boundary, with explicitly bounded guarantees;
- owned-process cleanup that remains best-effort under `BaseException` and
  signals without suppressing the original failure;
- honest deadlines across every save and transfer phase, including blocking
  operations, or clearly documented limits where a hard bound is impossible.

The proposed runner does not currently provide these guarantees. No native
run should be inferred from the existence of this checker.
