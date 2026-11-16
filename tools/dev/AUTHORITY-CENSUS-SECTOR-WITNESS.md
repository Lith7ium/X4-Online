# Census saved-sector witness candidates

`authority_census_sector_witness_evidence.py` is a read-only offline lookup for
one exact sector macro in the pinned, confirmed census checkpoint. It first
reuses the existing checkpoint/marker/registry provenance verifier, including
the saved forward/reverse registry bijection. Two additional digest-checked
streaming passes join saved sector ancestry and that same forward table. The
selected saved sector must exist exactly once, every saved sector macro must be
case-insensitively unique. The selected sector and each returned witness ID
must not collide with another serialized universe component, including
alternative hex capitalization and leading-zero spellings. Missing, duplicate, malformed,
changed, unconfirmed or inconsistent inputs fail closed. The selected sector
must have at least one saved registered ship candidate.

The result contains the saved sector component reference and sorted registry
indices whose serialized ship components have that saved sector ancestor. The
per-index flags describe only saved XML ancestry: whether a docking bay is an
ancestor and whether the immediate component parent is a zone. Unregistered
ships do not become witness indices. These are candidates, not a guarantee that
a ship is currently operational, undocked, present in the same sector or
valid in any loaded process. The saved reference is a diagnostic value and
must never be sent as a runtime handle or used alone as a network identity.

No runtime actor, sector handle, loaded file, sector-coordinate frame, complete
universe coverage or cross-instance binding is established. Later native work
must independently resolve each selected registry index in each process,
validate its actor/sector relationship and current docking/storage state, and
compare local sector lookup with the locally verified actor's sector. A missing
or moved witness is inconclusive. Saved macro uniqueness applies only to this
recorded checkpoint and does not cover dynamic sectors or other saves/mods.

The full provenance check uses five compressed-save/XML streaming passes; the
lookup uses two more. They are digest checked, not adversarial filesystem
transactions, and should not be repeated needlessly. The synthetic tests run
without reading the census archive or starting X4:

```
python3 -m unittest discover -s tests -p test_authority_census_sector_witness_evidence.py -v
```

When a single lookup is actually needed, its exact target can be supplied via
`--sector-macro` and optional `--store`. The tool never modifies the archive.
