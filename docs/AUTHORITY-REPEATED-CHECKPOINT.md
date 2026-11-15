# Repeated same-slot checkpoint experiment

`tools/dev/authority_reuse_live.py` explicitly starts one isolated Linux X4
process in a fresh disposable profile. It uses the actual opt-in repeated-save
control state and requests three pauses and saves to the same initially empty
slot. After each native save event, its supervisor independently publishes a
checkpoint, verifies its gzip/XML content, digest, unique request-bound title
and advancing game time, and only then authorizes resume. It does not mount a
normal user profile writable or use the lockstep gate. It is not an integrated
multiplayer lifecycle or an Internet service.

One native run completed all three save/verify/resume cycles on the pinned
Linux X4 installation. The immutable checkpoints had three different contents
and strictly increasing game times. The test-owned X4 process exited, and the
checked Steam identity remained unchanged. This establishes that this isolated
same-slot sequence worked in one process; it does not prove arbitrary repeated
saves, concurrent saves, recovery after a crash, automatic last-disconnect
saving, client admission or Windows operation.

A separate isolated X4 process subsequently loaded the third checkpoint. The
loader independently rechecked all three source checkpoints and their ordered
receipts, staged the third save read-only, requested that slot, observed a valid
player and advancing game time, and checked that the loaded time did not regress
behind the saved time. The staged file remained unchanged; the owned process
exited and the checked Steam identity remained unchanged. The staged bytes and
time checks provide supporting evidence but do not directly identify the file
descriptor consumed by X4 or prove complete world-state identity. This does
not establish a network join or cross-platform save compatibility.

To repeat the isolated experiment, close other X4 instances and explicitly use a
fresh output directory under `.local`:

```sh
python3 tools/dev/authority_reuse_live.py --game /path/to/X4 \
  --out .local/reuse-example --display :0
```

Private save bytes, identifiers and raw logs remain in the 0700 output
directory. `tests/test_authority_reuse_live.py` uses isolated doubles and
temporary files; it does not launch X4.
