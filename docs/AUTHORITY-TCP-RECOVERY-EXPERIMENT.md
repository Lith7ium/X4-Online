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

The isolated native Linux run `.local/authority-tcp-recovery-01` succeeded.
Its source was the TCP departure checkpoint
`checkpoint-5e8e1f852bc84f8b90f6c30c24bd3432`, SHA-256
`71042e25b0d2560f35fbc44fc6f0bcdd688936c153b0d9f7c2fe71fc03cffc1e`.
The staged save's SHA-256 matched that source. The X4 log records the request to
load `save_008`, both load passes, the expected saved marker after the game-load
event, and a pause observation in that order. The runner then recorded bridge
activation and a paused coordinator after a synthetic waiting join, with a new
confirmed marked checkpoint `checkpoint-cdbae20de21c4a47901061374a196c70`,
SHA-256 `36833a68e8549c6b5ca105db3dbcbc183c0a0257aa9b0a30ff212639d2e2f018`.
Its `CURRENT` and `CONFIRMED` pointers match, and the runner reported no owned
processes remaining. An independent offline check verified the fresh marker in
the saved bytes. The installed identity fixture's bytes match the archived
source. No client was admitted and no gameplay was tested. The startup log also
reports read-only `config.xml` write failures, an FSR3 queue error, and a missing
extension icon signature; these messages did not prevent the recorded run.
