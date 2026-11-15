# Recovery from the recorded TCP departure checkpoint

`tools/dev/authority_recovery_bridge_live.py` retains its original marked-bridge
source by default. The explicit `--source-type tcp-last-disconnect` option
accepts only `.local/authority-tcp-last-disconnect-01/checkpoints` and the
recorded checkpoint ID, SHA-256, size and saved `MarkerState` marker. It checks
that `CURRENT` and `CONFIRMED` match, the completed source result describes the
simulated final TCP disconnect and successful owned cleanup, and the archived
server's extension configuration matches the disposable recovery profile.
The existing runner requires output and the entire source experiment to be
disjoint. The checkpoint is copied to a private new profile; the source remains
unchanged.

The source save contains persistent `X4AuthorityIdentity` state. Its archived
MD fixture is checked against both a pinned digest and the repository copy,
then copied byte for byte into the private recovery overlay and included in the
protected, read-only bind set. The fixture's spawn cue requires a specific UI
event; the recovery overlay does not install or invoke the identity spawn UI.
The source server fixture was not independently protected by read-only binds
during the historical TCP run. The currently archived bytes and their match to
the repository therefore do not independently prove which bytes ran then.
Retaining the script does not itself prove that its saved references were
restored correctly or that no duplicate ships exist.

The opt-in experiment observes a load-event marker and pause, activates a local
bridge, and attempts a new marked checkpoint after a synthetic waiting join.
The TCP disconnect in the source was simulated and its client X4 continued
running until cleanup. Even a successful recovery experiment would not prove
every byte consumed by X4, no simulation before pause, client re-admission,
gameplay, cross-platform behavior, or full persistent-world correctness.
Source file identity checks are point-in-time checks, not an adversarial lock.
