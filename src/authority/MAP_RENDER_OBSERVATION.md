# Local map renderer observation

`lua/map_render_observation.lua` reads the raw component list of the currently
shown `MapMenu`. It is a client-side observation primitive for investigating
on-demand position interest. It does not establish that the native list is
clipped to the camera viewport or respects radar knowledge. No subscription,
position request, portable identity binding or network transmission is enabled.

An existing UI owner can explicitly construct and call it:

```lua
local sampler = assert(X4LAN_MAP_RENDER_OBSERVATION.new_x4({
    enabled = true,
    max_components = 65536,
}))
local observation, reason = sampler:sample()
```

Import registers no hooks and makes no native calls. Construction loads FFI
only when enabled. `sample()` looks up the shown map in `Menus`, then reads
`GetNumMapRenderedComponents` / `GetMapRenderedComponents` using its current
holomap handle. A result has `map_open`, `raw_count` and `component_ids`.
IDs are exact decimal uint64 strings, local to this X4 process. Raw order,
duplicates and zero entries are preserved. The count describes raw components,
not distinct ships. The module deliberately does not use the menu's enriched
`renderedComponents`, which also includes selected/targeted and internally
stored objects.

A closed or not-yet-created map returns an explicit empty, closed observation
without native enumeration. A failed read, changed menu/handle/count or exceeded
bound returns `nil, reason`, never a partial list. The default bound is 65,536
components and the configurable maximum is one million. A later caller-owned
sample may succeed; the sampler does not retry or retain old results. Count and
handle checks are sampled, not an atomic engine snapshot: equal counts do not
prove the same object set throughout the call. Invalid or non-ship entries need
separate inspection before a future interest decision.

## Evidence and next check

The locally extracted vanilla source at
`work/x4-playtest7/.local/engine-reference/ui/addons/ego_detailmonitor/menu_map.lua`
declares these functions at lines 648 and 703 and reads the raw list in
`updateRenderedComponents` at line 7414, before enriching it. Its SHA-256 is
`6c56ba3881495ad8ee7db3a144c16079f2b2eaad56a3a1e5efe171f899fd6865`.
The adjacent `ego_detailmonitorhelper/helper.lua` sets `menu.shown` on open
(line 1395) and clears it on close (line 1623). The installed Linux executable
exports both native functions. These are static observations, not an ABI or
viewport-behavior test; no game source is copied into this module.

The focused offline test passed, including the enabled X4 adapter with real
LuaJIT uint64 buffers and simulated native getters. It preserves
`9007199254740993` exactly, omits enriched-menu-only entries, and makes no native
enumeration calls for a closed map. No X4, Windows, Internet or full-suite run
was performed for this change.

The subsequent [single Linux native run](../../reports/AUTHORITY-MAP-RENDER-NATIVE-20261118.md)
passed a closed/open/closed map lifecycle. The opened map returned one raw local
component, and owned-process cleanup completed. This validates the basic native
read path for that case, not viewport/radar semantics or useful ship coverage.

The next native check should vary pan, zoom, map filters and an offscreen
selection while comparing raw lists and identified components.
`authority_sector_read_live.py` supplies an existing
single-X4 load/cleanup owner; its `state == 'done'` update path can call a private
probe without adding another update hook. Its old checkpoint requires the
archived registry script, independently pinned to SHA-256
`8b7c9887c9c1476e45fe84a60243547d96e09b11d4c40fabd151930af517e939`,
rather than today's changed script. The private runner and its source hashes
are recorded in the native report. Only after native semantics are established
should these local observations drive server interest.
