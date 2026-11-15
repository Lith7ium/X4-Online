# Local participant control

`local_participant_control.py` extracts the loopback pause/resume adapter from
`tools/dev/authority_two_x4_resume_live.py`. It is inactive unless explicitly
constructed with `enabled=True`. It controls one participant handle and can be
passed as the `participants` adapter to `WorldCoordinator` after the supervisor
has enrolled a peer and assigned its session handle. The existing disposable
Linux X4 experiment now uses this component; the paired Lua endpoint remains
`tools/dev/authority_two_x4_participant_probe.lua` and is also experimental.

The supervisor must own and independently verify the X4 process, protect the
per-controller lease in a private configuration, serialize all controller calls,
and fence the process after an indeterminate command or enrollment. The lease
and loopback source pinning do not establish process identity on their own. A
receipt confirms only what the paired endpoint reports. A single controller does
not transfer or verify a save, admit a player, or implement remote transport.
It must not be exposed directly to the Internet.

The pre-existing native two-X4 experiment established pause and resume using the
same protocol before this extraction. The extracted component has focused
synthetic loopback tests; no fresh native run or Windows behavior has been
established by this change.

`LocalParticipantGroup` maps session handles to these independent local
controllers and implements the same pause/resume interface for multiple ready
participants. Its caller serializes registration, removal and operations. It
is bound to one valid world epoch and verifies each controller belongs to that
epoch both at attachment and before dispatch. It validates the entire requested
handle set before dispatch; a failure once dispatch starts permanently faults
the group because earlier participants may
already have changed state. A supervisor must fence or settle the affected
processes before replacing it. This mapping is local and makes no claims about
remote identity, networking or loaded saves.
