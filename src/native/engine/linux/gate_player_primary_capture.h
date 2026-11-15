#ifndef X4_GATE_PLAYER_PRIMARY_CAPTURE_H
#define X4_GATE_PLAYER_PRIMARY_CAPTURE_H

#include "player_primary_capture.h"
#include "player_space_context_vector.h"

/* Separate from the generic15 wrapper contract. Both registered native fire
 * families are suppressed; outgoing stock records remain unchanged. All
 * storage and wrappers stay resident through partial installation and STOP. */
typedef struct {
    uintptr_t node, original, replacement;
    unsigned kind, id, family, swapped;
} primary_capture_handler;

static struct {
    unsigned configured, requested, attempted;
    _Atomic unsigned installed;
    uintptr_t owner;
    uint64_t sealed;
    unsigned sealed_held;
    primary_capture_handler handlers[16];
    player_space_vector_installation context[2];
    primary_capture_state state;
    _Atomic unsigned busy, clear_context;
} player_fire_capture;

static _Noreturn void primary_capture_fatal(const char *reason) {
    /* Literal call-site reasons only. One bounded write, with no formatting,
     * allocation, stdio lock, retry or cleanup in an unknown callback context. */
    static const char prefix[] = "X4LAN PRIMARY_CAPTURE terminal reason=";
    char message[sizeof prefix + 80];
    size_t length = sizeof prefix - 1;
    memcpy(message, prefix, length);
    for (size_t index = 0; index < 79 && reason[index]; ++index) {
        message[length++] = reason[index];
    }
    message[length++] = '\n';
    (void)write(STDERR_FILENO, message, length);
    _exit(225);
}

static void primary_capture_require(int valid, const char *reason) {
    if (!valid) {
        primary_capture_fatal(reason);
    }
}

static int primary_capture_pins(void) {
    static const lx_site pins[] = {
        {"fire-capture-state0",0x1247080,648,"335612612b94f850512c9481965e909ce0bc0dad28c08e3333cb463df681a4ba"},
        {"fire-capture-range0",0x1247310,281,"67991cac67efeee98fd43c1b47872aa3bd2b676e39c3c213888723d3b646e9a7"},
        {"fire-capture-context0",0x1247430,34,"e30abad005aecf7450b365de40bdf4321d92942031acf8a45fe4d583468e58cb"},
        {"fire-capture-state1",0x1247460,293,"48b01b7c475c5567ef1aa03704114f0af58c2afa012b22b1778ce2990767979b"},
        {"fire-capture-range1",0x1247590,90,"92cef2c714524c5d540d3993afd7bf1e3bdbeec6f592a58410006f5ac22c41bf"},
        {"fire-capture-context1",0x12475f0,34,"e7b6f68256ef50194772232d301ae5dd9a54630e44ab3e6aa7c9c43669ec7dd4"},
    };
    for (unsigned index = 0; index < sizeof pins / sizeof pins[0]; ++index) {
        if (!site_ok(&pins[index])) {
            return 0;
        }
    }
    uint32_t threshold = 0;
    return stock_observer_pins(NULL) && gate_read_local(LX(0x2e25d80), &threshold, 4) &&
        threshold == UINT32_C(0x38d1b717);
}

static void primary_capture_dispatch(unsigned family, unsigned kind, unsigned id, uint32_t raw, uintptr_t caller);
static void primary_capture_state0(int id, unsigned char held) {
    primary_capture_dispatch(0, 1, (unsigned)id, held, (uintptr_t)__builtin_return_address(0));
}
static void primary_capture_state1(int id, unsigned char held) {
    primary_capture_dispatch(1, 1, (unsigned)id, held, (uintptr_t)__builtin_return_address(0));
}
static void primary_capture_range0(int id, float value) {
    uint32_t raw;
    memcpy(&raw, &value, 4);
    primary_capture_dispatch(0, 2, (unsigned)id, raw, (uintptr_t)__builtin_return_address(0));
}
static void primary_capture_range1(int id, float value) {
    uint32_t raw;
    memcpy(&raw, &value, 4);
    primary_capture_dispatch(1, 2, (unsigned)id, raw, (uintptr_t)__builtin_return_address(0));
}

static void primary_capture_context(int context) {
    int saved_errno = errno;
    primary_capture_require(!atomic_exchange_explicit(&player_fire_capture.busy, 1, memory_order_acq_rel),
                            "fire_capture_context_concurrent");
    if (context == 8) {
        /* Context callbacks may originate outside InputBase::Move. They only
         * publish a private clear request; no phase reset or engine call. */
        atomic_store_explicit(&player_fire_capture.clear_context, 1u, memory_order_release);
    }
    atomic_store_explicit(&player_fire_capture.busy, 0, memory_order_release);
    errno = saved_errno;
}

static void primary_capture_context0(int context) { primary_capture_context(context); }
static void primary_capture_context1(int context) { primary_capture_context(context); }

static uintptr_t primary_capture_wrapper(unsigned family, unsigned kind) {
    if (kind == 1) return family ? (uintptr_t)primary_capture_state1 : (uintptr_t)primary_capture_state0;
    return family ? (uintptr_t)primary_capture_range1 : (uintptr_t)primary_capture_range0;
}

static int primary_capture_id(unsigned kind, unsigned id) {
    return kind == 1 ? id == 0x18 || id == 0x19 || id == 0x30 || id == 0x31 :
        kind == 2 && id >= 0x11 && id <= 0x14;
}

/* Failure-only evidence from the already completed census. Never retry native
 * reads or inspect a partial census; keep unknown registrations fail-closed. */
static size_t primary_capture_tree_literal(char *out, size_t used, const char *text) {
    while (*text && used < 511) out[used++] = *text++;
    return used;
}

static void primary_capture_tree_write(const char *reason, const char *const names[],
                                        const uint64_t values[], unsigned count) {
    static const char digits[] = "0123456789abcdef";
    char row[512];
    size_t used = primary_capture_tree_literal(row, 0, "X4LAN PRIMARY_CAPTURE tree_v=1 reason=");
    used = primary_capture_tree_literal(row, used, reason);
    for (unsigned field = 0; field < count; ++field) {
        used = primary_capture_tree_literal(row, used, names[field]);
        for (unsigned shift = 64; shift && used < 511; shift -= 4) {
            row[used++] = digits[(values[field] >> (shift - 4)) & 15];
        }
    }
    row[used++] = '\n';
    (void)write(STDERR_FILENO, row, used);
}

static int primary_capture_scan_refuse(const char *reason, unsigned census,
                                        unsigned count, unsigned accepted, uintptr_t owner) {
    unsigned selected = 0;
    if (census) {
        for (unsigned index = 0; index < count; ++index) {
            if (primary_capture_id(sko_scratch[index].kind, (unsigned)sko_scratch[index].key)) ++selected;
        }
    }
    unsigned shown = selected < 32 ? selected : 32;
    const char *names[] = {" tick=", " census=", " owner=", " expected_owner=", " nodes=",
                           " accepted=", " selected=", " shown=", " omitted="};
    const uint64_t values[] = {stats.issued, census, owner, sko_session.owner, count,
                               accepted, selected, shown, selected - shown};
    primary_capture_tree_write(reason, names, values, 9);
    for (unsigned index = 0, emitted = 0; census && index < count && emitted < shown; ++index) {
        const sko_node *node = &sko_scratch[index];
        if (!primary_capture_id(node->kind, (unsigned)node->key)) continue;
        const char *fields[] = {" index=", " kind=", " id=", " node=", " handler="};
        const uint64_t row[] = {emitted++, node->kind, (uint64_t)node->key, node->address, node->handler};
        primary_capture_tree_write("registration", fields, row, 5);
    }
    return 0;
}

static int primary_capture_scan(primary_capture_handler output[16], uintptr_t *owner) {
    unsigned count = 0, used = 0;
    if (!sko_census(sko_scratch, &count, owner))
        return primary_capture_scan_refuse("census", 0, 0, 0, 0);
    if (*owner != sko_session.owner)
        return primary_capture_scan_refuse("owner", 1, count, 0, *owner);
    for (unsigned index = 0; index < count; ++index) {
        const sko_node *node = &sko_scratch[index];
        if (!primary_capture_id(node->kind, (unsigned)node->key)) continue;
        unsigned family;
        for (family = 0; family < 2; ++family) {
            unsigned original_va = node->kind == 1 ? (family ? 0x1247460 : 0x1247080) :
                                                   (family ? 0x1247590 : 0x1247310);
            uintptr_t original = (uintptr_t)LX(original_va);
            uintptr_t wrapper = primary_capture_wrapper(family, node->kind);
            if (node->handler != original && node->handler != wrapper) continue;
            if (used == 16)
                return primary_capture_scan_refuse("too_many", 1, count, used, *owner);
            for (unsigned other = 0; other < used; ++other) {
                if (output[other].family == family && output[other].kind == node->kind &&
                    output[other].id == (unsigned)node->key)
                    return primary_capture_scan_refuse("duplicate", 1, count, used, *owner);
            }
            output[used++] = (primary_capture_handler){node->address, original, wrapper,
                node->kind, (unsigned)node->key, family, node->handler == wrapper};
            break;
        }
        /* A third callback for a fire ID has not been authenticated as inert.
         * Reject it rather than leaving an unowned native fire path. */
        if (family == 2)
            return primary_capture_scan_refuse("unknown_handler", 1, count, used, *owner);
    }
    return used == 16 ? 1 : primary_capture_scan_refuse("missing", 1, count, used, *owner);
}

static int primary_capture_fresh(void) {
    primary_capture_handler now[16] = {{0}};
    uintptr_t owner = 0;
    if (!primary_capture_scan(now, &owner) || owner != player_fire_capture.owner) return 0;
    for (unsigned index = 0; index < 16; ++index) {
        const primary_capture_handler *expected = &player_fire_capture.handlers[index];
        unsigned found = 0;
        for (unsigned other = 0; other < 16; ++other) {
            if (now[other].node == expected->node && now[other].kind == expected->kind &&
                now[other].id == expected->id && now[other].family == expected->family &&
                now[other].swapped == expected->swapped) ++found;
        }
        if (found != 1) return 0;
    }
    return 1;
}

static int primary_capture_context_owned(void) {
    player_space_vector_snapshot now;
    if (player_space_vector_snapshot_read(&player_space_ops.vector, player_fire_capture.owner, &now) != PLAYER_SPACE_VECTOR_OK) return 0;
    for (unsigned family = 0; family < 2; ++family) {
        const player_space_vector_installation *owned = &player_fire_capture.context[family];
        if (!owned->verified || owned->begin != now.begin || owned->end != now.end || owned->capacity != now.capacity ||
            owned->slot < now.begin || owned->slot >= now.end ||
            now.entries[(owned->slot - now.begin) / 8] != owned->replacement) return 0;
        unsigned originals = 0, replacements = 0;
        for (size_t index = 0; index < now.count; ++index) {
            originals += now.entries[index] == owned->original;
            replacements += now.entries[index] == owned->replacement;
        }
        if (originals || replacements != 1) return 0;
    }
    return 1;
}

static int primary_capture_banks_neutral(void) {
    static const unsigned banks[] = {0x3e5b29b,0x3e5b29c,0x3e5b29d,0x3e5b29e,
                                    0x3e77cb0,0x3e77cb1,0x3eacc40,0x3eacc41};
    for (unsigned index = 0; index < sizeof banks / sizeof banks[0]; ++index) {
        unsigned char value = 1;
        if (!gate_read_local(LX(banks[index]), &value, 1) || value) return 0;
    }
    unsigned char flags = 255;
    return factory_probe_player1 && gate_read_local((void *)(factory_probe_player1 + 0x8a540), &flags, 1) && !(flags & 7);
}

static int primary_capture_local_context(unsigned *active) {
    if (player_space_mode()) return player_space_local_state(active);
    unsigned char value = 2;
    if (!gate_read_local((void *)(player_fire_capture.owner + 0xcf0), &value, 1) || value > 1) return 0;
    *active = value;
    return 1;
}

static int player_primary_capture_request(unsigned independent) {
    if (player_fire_capture.configured) return 0;
    player_fire_capture.configured = 1;
    const char *setting = getenv("X4_DEV_PRIMARY_CAPTURE");
    if (!setting) return 1;
    if (strcmp(setting,"capture-v1") || independent != 1 || !player_cursor_mode() ||
        !player_stock_focus_wanted() || player_startup()->version != 1 ||
        (getenv("X4_DEV_PRIMARY_TRIGGER") && strcmp(getenv("X4_DEV_PRIMARY_TRIGGER"), "human-v1"))) return 0;
    player_fire_capture.requested = 1;
    return 1;
}

static int player_primary_capture_admit(uint64_t generation) {
    if (!player_fire_capture.requested || generation < keyboard_probe_queue.config.first_capture) return 1;
    primary_capture_require(keyboard_probe_queue.config.last_capture >= keyboard_probe_queue.config.first_capture + 179 &&
        keyboard_probe_queue.config.last_capture <= keyboard_probe_queue.config.first_capture + 899 &&
        player_dispatch_enabled && factory_probe_main_boundary() && stock_observer_slot_valid() &&
        stock_observer_main_boundary &&
        GetCurrentThreadId() == main_thread && !atomic_load(&stock_observer_input_depth) &&
        !atomic_load(&player_fire_capture.busy) && keyboard_probe_identity() && primary_capture_pins() &&
        primary_capture_banks_neutral(), "fire_capture_admission");
    if (!player_fire_capture.installed) {
        primary_capture_require(!player_fire_capture.attempted && generation == keyboard_probe_queue.config.first_capture,
                                "fire_capture_install_epoch");
        player_fire_capture.attempted = 1;
        primary_capture_require(primary_capture_scan(player_fire_capture.handlers, &player_fire_capture.owner), "fire_capture_tree");
        for (unsigned index = 0; index < 16; ++index) {
            primary_capture_handler *entry = &player_fire_capture.handlers[index];
            primary_capture_require(!entry->swapped && primary_capture_fresh(), "fire_capture_before_cas");
            primary_capture_require(stock_observer_swap_node(NULL, entry->node + 0x28,
                entry->original, entry->replacement) == SKO_CAS_APPLIED, "fire_capture_cas");
            entry->swapped = 1;
            primary_capture_require(primary_capture_fresh(), "fire_capture_after_cas");
        }
        for (unsigned family = 0; family < 2; ++family) {
            uintptr_t original = (uintptr_t)LX(family ? 0x12475f0 : 0x1247430);
            uintptr_t replacement = family ? (uintptr_t)primary_capture_context1 : (uintptr_t)primary_capture_context0;
            primary_capture_require(player_space_vector_install(&player_space_ops.vector, player_fire_capture.owner,
                original, replacement, &player_fire_capture.context[family]) == PLAYER_SPACE_VECTOR_OK,
                "fire_capture_context_install");
        }
        player_fire_capture.installed = 1;
    }
    primary_capture_require(primary_capture_fresh() && primary_capture_context_owned(), "fire_capture_ownership");
    unsigned context = 2;
    primary_capture_require(primary_capture_local_context(&context),
                            "fire_capture_context_read");
    primary_capture_require(!player_fire_capture.state.generation ||
        player_fire_capture.state.generation > keyboard_probe_queue.config.last_capture ||
        player_fire_capture.sealed == player_fire_capture.state.generation, "fire_capture_missing_seal");
    primary_capture_require(primary_capture_begin(&player_fire_capture.state, generation, context), "fire_capture_begin");
    if (generation > keyboard_probe_queue.config.last_capture) primary_capture_clear(&player_fire_capture.state);
    return 1;
}

static void primary_capture_apply_clear(void) {
    unsigned pending = atomic_exchange_explicit(&player_fire_capture.clear_context, 0, memory_order_acq_rel);
    if (pending) {
        primary_capture_clear(&player_fire_capture.state);
    }
}

static void primary_capture_dispatch(unsigned family, unsigned kind, unsigned id, uint32_t raw, uintptr_t caller) {
    int saved_errno = errno;
    primary_capture_require(player_fire_capture.installed &&
        !atomic_exchange_explicit(&player_fire_capture.busy, 1, memory_order_acq_rel), "fire_capture_callback_install");
    primary_capture_require(keyboard_probe_worker() && atomic_load(&stock_observer_input_depth) == 1 &&
        keyboard_probe_queue.tick == stats.issued && player_fire_capture.state.generation == stats.issued &&
        keyboard_probe_identity() && primary_capture_id(kind,id) &&
        caller == (uintptr_t)LX(kind == 1 ? 0x1051074 : 0xced008), "fire_capture_callback_phase");
    if (stats.issued <= keyboard_probe_queue.config.last_capture) {
        unsigned focused = 0, context = 2;
        unsigned char blocked = 2;
        primary_capture_apply_clear();
        primary_capture_require(primary_capture_local_context(&context) &&
            player_stock_focus_read(stats.issued, &focused) &&
            gate_read_local(LX(0x3e5b2a0), &blocked, 1) && blocked <= 1 &&
            primary_capture_focus(&player_fire_capture.state, focused), "fire_capture_event_context");
        if (!context) primary_capture_clear(&player_fire_capture.state);
        player_fire_capture.state.context = context;
        primary_capture_require(primary_capture_event(&player_fire_capture.state, family, kind, id, raw, blocked), "fire_capture_event");
    } else {
        primary_capture_clear(&player_fire_capture.state);
    }
    atomic_store_explicit(&player_fire_capture.busy, 0, memory_order_release);
    errno = saved_errno;
}

/* Flush outside native callback execution; do not put FIRE into the wire. */
static int player_primary_capture_seal(uint64_t generation) {
    if (!player_fire_capture.requested) return 1;
    if (generation < keyboard_probe_queue.config.first_capture ||
        generation > keyboard_probe_queue.config.last_capture) return 1;
    primary_capture_require(player_fire_capture.installed &&
        !atomic_exchange_explicit(&player_fire_capture.busy, 1, memory_order_acq_rel) &&
        generation != player_fire_capture.sealed && keyboard_probe_worker() && stock_observer_worker_boundary() && primary_capture_fresh() &&
        primary_capture_context_owned() && primary_capture_banks_neutral() &&
        generation == player_fire_capture.state.generation, "fire_capture_seal");
    unsigned focused = 0, context = 2;
    unsigned char blocked = 2;
    primary_capture_apply_clear();
    primary_capture_require(primary_capture_local_context(&context) && player_stock_focus_read(generation, &focused) &&
        gate_read_local(LX(0x3e5b2a0), &blocked, 1) &&
        primary_capture_block(&player_fire_capture.state, blocked) &&
        primary_capture_focus(&player_fire_capture.state, focused), "fire_capture_focus");
    if (!context) primary_capture_clear(&player_fire_capture.state);
    player_fire_capture.state.context = context;
    int saved_errno = errno;
    for (unsigned index = 0; index < player_fire_capture.state.count; ++index) {
        const primary_capture_edge *edge = &player_fire_capture.state.edges[index];
        primary_capture_require(dprintf(2,
            "X4LAN PRIMARY_CAPTURE v=1 stage=edge tick=%llu index=%u family=%u kind=%u id=%u raw=%08x held=%u primary=%u focused=%u context=%u native_forward=0\n",
            (unsigned long long)generation, index, edge->family, edge->kind, edge->id, edge->raw,
            edge->held, edge->primary, edge->focused, edge->context) > 0, "fire_capture_edge_receipt");
    }
    primary_capture_require(dprintf(2,
        "X4LAN PRIMARY_CAPTURE v=1 stage=held tick=%llu slot=%u focused=%u context=%u held=%u edges=%u banks_neutral=1 wire_fire=0 native_forward=0\n",
        (unsigned long long)generation, stats.slot, focused, player_fire_capture.state.context,
        primary_capture_held(&player_fire_capture.state), player_fire_capture.state.count) > 0, "fire_capture_held_receipt");
    player_fire_capture.state.count = 0;
    player_fire_capture.sealed_held = primary_capture_held(&player_fire_capture.state);
    player_fire_capture.sealed = generation;
    atomic_store_explicit(&player_fire_capture.busy, 0, memory_order_release);
    errno = saved_errno;
    return 1;
}
/* Immutable handoff for a subsequent explicit human-FIRE mode. Reading does
 * not reseal, mutate capture history or admit anything into today's wire. */
static inline int player_primary_capture_sample(uint64_t generation, unsigned *held) {
    if (!held || !player_fire_capture.requested || !player_fire_capture.installed ||
        player_fire_capture.sealed != generation || stats.issued != generation ||
        !keyboard_probe_worker() || !stock_observer_worker_boundary()) return 0;
    if (atomic_exchange_explicit(&player_fire_capture.busy, 1, memory_order_acq_rel)) return 0;
    unsigned valid = !atomic_load_explicit(&player_fire_capture.clear_context, memory_order_acquire);
    if (valid) *held = player_fire_capture.sealed_held;
    atomic_store_explicit(&player_fire_capture.busy, 0, memory_order_release);
    return valid;
}
#endif
