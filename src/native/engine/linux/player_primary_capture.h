#ifndef X4_PLAYER_PRIMARY_CAPTURE_H
#define X4_PLAYER_PRIMARY_CAPTURE_H

#include <math.h>
#include <stdint.h>
#include <string.h>

#define PRIMARY_CAPTURE_EDGES 128u

typedef struct {
    unsigned family, kind, id, held, primary, focused, context;
    uint32_t raw;
} primary_capture_edge;

typedef struct {
    uint64_t generation;
    unsigned channels[2][4], armed[2][4];
    unsigned focused, focus_known, context, blocked, block_known, count, failed;
    primary_capture_edge edges[PRIMARY_CAPTURE_EDGES];
} primary_capture_state;

static inline unsigned primary_capture_held(const primary_capture_state *state) {
    for (unsigned family = 0; family < 2; ++family) {
        for (unsigned channel = 0; channel < 4; ++channel) {
            if (state->channels[family][channel]) return 1;
        }
    }
    return 0;
}

static inline void primary_capture_clear(primary_capture_state *state) {
    memset(state->channels, 0, sizeof state->channels);
    memset(state->armed, 0, sizeof state->armed);
}

static inline int primary_capture_begin(primary_capture_state *state, uint64_t generation,
                                         unsigned context) {
    if (!state || state->failed || !generation || context > 1 || state->count ||
        (state->generation && generation != state->generation + 1)) return 0;
    if (!state->generation) {
        for (unsigned family = 0; family < 2; ++family) {
            for (unsigned channel = 0; channel < 4; ++channel) state->armed[family][channel] = 1;
        }
        if (!context) primary_capture_clear(state);
    } else if (!context && state->context) {
        primary_capture_clear(state);
    }
    state->generation = generation;
    state->context = context;
    return 1;
}

static inline int primary_capture_focus(primary_capture_state *state, unsigned focused) {
    if (!state || state->failed || focused > 1) return 0;
    if (!focused && (!state->focus_known || state->focused)) primary_capture_clear(state);
    state->focused = focused;
    state->focus_known = 1;
    return 1;
}

/* The native family0 primary input gate is also sampled when no callback
 * occurs. A rising gate invalidates held state and release-to-rearm history. */
static inline int primary_capture_block(primary_capture_state *state, unsigned blocked) {
    if (!state || state->failed || blocked > 1) return 0;
    if (blocked && (!state->block_known || !state->blocked)) primary_capture_clear(state);
    state->blocked = blocked;
    state->block_known = 1;
    return 1;
}

/* Native range handlers compare fabs(value) against these exact float bits.
 * No device sampling or game handler invocation happens here. */
static inline int primary_capture_event(primary_capture_state *state, unsigned family,
                                         unsigned kind, unsigned id, uint32_t raw, unsigned blocked) {
    if (!state || state->failed || !state->generation || family > 1 || blocked > 1 ||
        (kind != 1 && kind != 2) || state->count == PRIMARY_CAPTURE_EDGES) return 0;
    unsigned channel, primary, held;
    if (kind == 1) {
        if (raw > 1 || (id != 0x18 && id != 0x30 && id != 0x19 && id != 0x31)) return 0;
        held = raw;
        primary = id == 0x18 || id == 0x30;
        channel = id == 0x18 ? 0 : 1;
    } else {
        if (id < 0x11 || id > 0x14) return 0;
        float value, threshold;
        uint32_t threshold_bits = UINT32_C(0x38d1b717);
        memcpy(&value, &raw, 4);
        memcpy(&threshold, &threshold_bits, 4);
        if (!isfinite(value)) return 0;
        held = fabsf(value) >= threshold;
        primary = id == 0x11 || id == 0x13;
        channel = id == 0x11 ? 2 : 3;
    }
    if (!primary_capture_block(state, blocked)) return 0;
    if (primary) {
        /* Releases clear even without focus. Engages require current local
         * focus/context; regaining focus does not resurrect a held source. */
        if (!held) {
            state->channels[family][channel] = 0;
            state->armed[family][channel] = 1;
        } else if (!state->focused || !state->context || blocked) {
            state->channels[family][channel] = 0;
            state->armed[family][channel] = 0;
        } else {
            state->channels[family][channel] = state->armed[family][channel];
        }
    }
    state->edges[state->count++] = (primary_capture_edge){
        family, kind, id, held, primary, state->focused, state->context, raw};
    return 1;
}
#endif
