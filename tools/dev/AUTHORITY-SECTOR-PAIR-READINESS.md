# Two-X4 saved-sector readiness preparation

This opt-in harness is a **readiness diagnostic only**, not a create, network
or multiplayer test. It stages independent copies of the pinned two-sector
checkpoint into two disposable profiles. Each is mounted read-only with its
private save directory, and each uses one load-update owner. The archive
marker, saved fixture and two-entry bidirectional registry are checked by the
existing offline verifiers. Output and the entire historical source experiment
must be disjoint. No game save, experiment network connection or Create action
is requested, and no create receiver or job observer is installed.

For each profile the loader records its own ticket, checks the saved marker,
pauses and reads fixture slot 2. A separate correlated MD read checks that the
saved registry still has exactly indices 1 and 2, fixture epochs and both
mapping directions match, and the ships and sectors are distinct and valid.
The Lua callback checks both local ship/sector relationships via FFI, compares
slot 2 to the previously observed local handles, and emits a role-specific
readiness receipt. The sole update owner continues checking pause, game time,
profile and both local relationships until process cleanup. Local handles never
leave their own X4 process.

Both processes must be simultaneously owned and alive at a sampled point, each
must have a fresh validated readiness log in the same poll, and their staged
save hashes must match the pinned checkpoint. The harness fences signals,
tracks both gated launches and owns a single global lock. It checks log prefix
continuity and protected files while running, stops only its tracked process
groups, then rechecks both final logs, both staged saves and the source archive
before publishing a single result. Unconfirmed stop retains the lock. There is
no helper process in this readiness-only harness; a later network integration
must add its own strictly confirmed helper ownership and cleanup before either
X4 process or the lock is released.

The input, process, pause and callback observations are sampled, not atomic.
They do not prove that X4 consumed exact staged bytes, that game time never
advanced before the first pause, globally unique sector identities, equality of
local handles between processes, autonomous-simulation reconciliation, network
transfer, Windows, internet, or multiplayer gameplay. FFI/MD semantics and the
new two-process orchestration have only offline/synthetic tests so far; no
native outcome is claimed. Any unconfirmed guard, late callback, timeout or
cleanup result invalidates the attempt. The future actual Create/TCP driver
must remain disabled until it and its counterpart are jointly reviewed.
