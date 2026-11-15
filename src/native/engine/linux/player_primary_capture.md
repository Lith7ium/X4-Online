# Bounded native primary capture

`--player-primary-capture` is an explicit capture-only experiment. It requires
worker dispatch, active-flight cursor/focus capture, T40 startup and matching
180..900 independent keyboard/physics frames. It cannot run with the scripted
primary trigger. The frozen v20 bundle sets `X4_DEV_PRIMARY_CAPTURE=capture-v1`;
inherited values are stripped. Existing stock FIRE policy and wire bytes are
unchanged. Local receipts do not prove human-input replay or weapon effects.

The adapter leases exactly sixteen STATE/RANGE callbacks: two native families,
four IDs per kind. Both primary and secondary originals are suppressed after
installation, including releases and external contexts. It also leases both
native fire context-vector callbacks before SPACE takes its vector snapshot.
Each context callback has ABI `void(int context)` and clears on EDI==8; RSI has
no meaning. Every native bank and Player+0x8a540 fire bit must already be neutral
and remain neutral. The adapter never writes those banks or calls originals. The pinned family0
primary gate at3e5b2a0 is read in callbacks and again at seal, including ticks
with no input callback. A rising gate clears and disarms private held sources;
unblocking alone cannot rearm them. Native STATE1247180/1247210 and
RANGE12473a8/12473e0 return early when this byte is nonzero. This establishes
a native primary input gate, not a universal weapon-operational predicate.

Installation uses the existing SPACE main/joined InputOwner exclusion:
`factory_probe_main_boundary`, authenticated current owner, main thread and no
input callback. Fresh tree/vector reads and CAS detect drift; they are not an
independent lifetime exclusion. Unknown/missing/duplicate callbacks, moved
allocation, partial publication, stale generation, wrong worker/caller, malformed
raw input and concurrent callbacks terminate225. A bounded literal reason is emitted with
one best-effort write before terminal exit; there is no stdio/allocation/retry. There is no rollback, native
restore or handler unregistration. Resident dispatch's terminal stop policy owns
process shutdown. Default-off installs nothing.

Each family has four independent primary sources. A clear/focus loss disarms
all sources until each observes a release. Repeated held notifications after
focus regain cannot engage. Context notifications publish a pending clear under
the same nonblocking atomic guard as input callbacks and capture sealing;
concurrent execution terminates rather than racing. Context regain alone never
arms a source. Secondary events are observed but cannot set primary held state.

Native pins are the installed Linux9.00 SHA256
`113f73d74570084f6ce18a659b365009eccf579fb66dbabb5dad2b1718045f20`.
Family0 STATE/RANGE/context:1247080/1247310/1247430;
family1:1247460/1247590/12475f0. STATE caller1051074 passes EDI/ESI;
RANGE callerced008 passes EDI/XMM0. The already pinned InputUpdate covers the
latter. Exact analog threshold bits are38d1b717, using finite absolute value.

Primary STATE IDs18/30 and RANGE11/13 are hexadecimal. Secondary IDs19/31,
12/14 remain suppressed. Two context handlers clear their own native fire banks
on context8; the replacements only affect private capture state. The known
PlayerShootController getter is mutating and is never called here.

Receipts cover capture ticks38 through last_capture (physics40 through end).
Each tick has at most128 raw native events followed by one held sample. Sealing
is exact-once and occurs outside native input callbacks. The collector requires
ordered full range, local slot, neutral-bank/no-forward/no-wire markers, raw
STATE/RANGE predicate consistency and accepted physics bound to the same stderr
hash. It preserves raw failure rows. A passing neutral run is capture readiness,
not human input acceptance. Active source bindings still require a root-owned
native test in a disposable profile.

## Registration refusal diagnostics

A rejected registration census emits `tree_v=1` records before the unchanged
terminal exit. The summary distinguishes failed census, owner drift, unknown
handler, duplicate, excess and missing registrations. It records at most 32
matching entries from the completed census, with a count of omitted entries.
Values are hexadecimal. No additional engine reads or admission retries occur.
The first native capture attempt predates these detailed receipts and remains
unexplained; the new diagnostic has offline fixture coverage only.
