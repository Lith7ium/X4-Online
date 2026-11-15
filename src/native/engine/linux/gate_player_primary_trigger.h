#ifndef X4_GATE_PLAYER_PRIMARY_TRIGGER_H
#define X4_GATE_PLAYER_PRIMARY_TRIGGER_H

#include "player_primary_trigger.h"
#include "player_weapon_groups.h"

/* Disposable, terminate-only experiment. No restore/unregister path exists.
 * Component references keep allocations alive; engine owner ordering plus fresh
 * identity checks govern controller ownership. No universal reader exclusion. */
typedef struct {
    uintptr_t groups[2], ids[2];
    int32_t selected;
    unsigned count;
    uint64_t values[PLAYER_WEAPON_IDS_MAX];
} primary_trigger_group;

typedef struct {
    player_weapon_item item;
    uintptr_t controller, initial_controller;
    unsigned retained;
} primary_trigger_gun;

typedef struct {
    uintptr_t ship;
    primary_trigger_group group;
    primary_trigger_gun guns[PLAYER_WEAPON_MAX];
    unsigned count;
} primary_trigger_slot;

static struct {
    unsigned configured, enabled, leased, human;
    unsigned wanted[2];
    uint64_t prepared, applied;
    primary_trigger_slot slots[2];
} primary_trigger;

static void primary_trigger_require(int condition, const char *reason) {
    lifecycle_discard_require(condition, reason);
}

static int primary_trigger_pins(void) {
    static const lx_site pins[] = {
        {"primary-construction-script", 0xdf7b00, 2196, "1bd56f73a14b8c0d504c6122b949bf7c6006bf7bbca18d979994c490ccf408da"},
        {"primary-install", 0x11339b0, 698, "66f696c6799ba4c5dc840518962e4b5e335aecb941831b2f456713527a630760"},
        {"primary-release", 0x1133830, 236, "a7480a9a7b7268407d97ccb1b5daa2f3ef4ef2185ccaa80c53ce7a5bd38d7bb8"},
        {"primary-set", 0x110f900, 13, "d5eb6781e79b98a43f146ce41b83b3a311440f7906c49502cb8896d5f5f20a34"},
        {"primary-allocate", 0x1a448b0, 10, "7671cad22d56d212230522af5bbc2bd1e7927f30ce8f80e5c4a9d102b5d44585"},
        {"primary-aligned-allocate", 0x1e23dc0, 379, "80d05002fb290d41a9be86ba44420750dc1df677fa454ea4cd14c849630d1b3e"},
        {"primary-event-send", 0x16c5fe0, 823, "59d9389b7bd231f2bcf43773a523bf5f2c5a6bdc081f9ea46a65046d23cfb031"},
        {"primary-event-parent", 0x189fa50, 116, "a724d97fd9793b6f39e86685ca6a876254c470b633053237c27fd02db2e980e8"},
        {"primary-register", 0x124ed60, 102, "b84c07dda68f1502f26cd6a1e3ac4f4a81a2582a8b68979907c16d53294b2d1b"},
        {"primary-unregister", 0x124ee80, 79, "23ce76f3c619c3955084a701a06930d794d2ec66d7db39b7afb8bcab6ed1443d"},
        {"primary-stop", 0x1254080, 565, "c8bbb45166224ac496d33b1b3fd79c440342cab34ae1af269d84b82435914eab"},
        {"primary-operational-layout", 0xc02cb0, 179, "62eed3ef6876e4607409a2bfaca5ccc64c8a2e1fe07549637631ed1adabc84a8"},
        {"primary-delete", 0x1271060, 120, "7ee6f60c0d455bca2fdd99e2b036475feeb4237513eb0b521b50492d8e9ddc5a"},
    };
    for (unsigned index = 0; index < sizeof pins / sizeof pins[0]; ++index) {
        if (!site_ok(&pins[index])) return 0;
    }
    static const unsigned slots[][2] = {
        {0x3c6c628, 0x18a7df0},
        {0x3b04028, 0x1271060}, {0x3b04078, 0x110f8e0},
        {0x3b040a8, 0x1089ed0}, {0x3b040c0, 0x124ed60},
        {0x3b040d0, 0x124ee80}, {0x3b040d8, 0x1254080},
        {0x3b04100, 0x110f900},
    };
    for (unsigned index = 0; index < sizeof slots / sizeof slots[0]; ++index) {
        uintptr_t target = 0;
        if (!gate_read_local(LX(slots[index][0]), &target, 8) ||
            target != (uintptr_t)LX(slots[index][1])) return 0;
    }
    return player_target_hold_pins();
}

static int primary_trigger_boundary(uint64_t generation) {
    return player_dispatch_enabled && player_dispatch_ticket == generation &&
        pwda_phase(&player_dispatch) == PWDA_JOINED && player_recurring_physics_entered() &&
        gate_tls_worker(gate_tls_self()) && generation == stats.issued &&
        generation == player_recurring_tail_token.generation && !player_network_busy &&
        !player_physics_replay_busy && keyboard_probe_identity() && player_physics_identity();
}

static int primary_trigger_group_read(uintptr_t ship, primary_trigger_group *group) {
    memset(group, 0, sizeof *group);
    if (!ship || ship > UINTPTR_MAX - 0x660 ||
        !gate_read_local((void *)(ship + 0x628), group->groups, 16) ||
        !gate_read_local((void *)(ship + 0x658), &group->selected, 4) ||
        group->groups[1] < group->groups[0] || (group->groups[1] - group->groups[0]) % 24 ||
        (group->groups[1] - group->groups[0]) / 24 > PLAYER_WEAPON_GROUP_MAX || group->selected < 0 ||
        (size_t)group->selected >= (group->groups[1] - group->groups[0]) / 24) return 0;
    uintptr_t selected = group->groups[0] + (size_t)group->selected * 24;
    if (selected < group->groups[0] || selected > UINTPTR_MAX - 16 ||
        !gate_read_local((void *)selected, group->ids, 16) || group->ids[1] < group->ids[0] ||
        (group->ids[1] - group->ids[0]) % 8 || (group->ids[1] - group->ids[0]) / 8 > PLAYER_WEAPON_IDS_MAX) return 0;
    group->count = (unsigned)((group->ids[1] - group->ids[0]) / 8);
    return !group->count || gate_read_local((void *)group->ids[0], group->values, group->count * 8);
}

static uintptr_t primary_trigger_pointer(uintptr_t address) {
    uintptr_t value = 0;
    primary_trigger_require(gate_read_local((void *)address, &value, 8), "primary_pointer");
    return value;
}

static void primary_trigger_verify(primary_trigger_slot *slot, primary_trigger_gun *gun, unsigned owned) {
    primary_trigger_group group;
    uint32_t class_gate = 1;
    unsigned char operational = 0;
    primary_trigger_require(gate_read_local((void *)(gun->item.object + 0x68), &class_gate, 4) && !class_gate &&
        gate_read_local((void *)(gun->item.object + 0xd1), &operational, 1) && operational == 1,
        "primary_gun_not_operational");
    primary_trigger_require(primary_trigger_group_read(slot->ship, &group) &&
        !memcmp(&group, &slot->group, sizeof group) &&
        player_fire_observation_resolve(NULL, gun->item.runtime) == gun->item.object &&
        player_fire_observation_under_ship(NULL, gun->item.object, slot->ship) == 1 &&
        primary_trigger_pointer(gun->item.object + 0x38) == (uintptr_t)LX(0x3c6c628), "primary_gun_identity");
    if (owned) {
        primary_trigger_require(gun->retained && gun->controller &&
            primary_trigger_pointer(gun->item.object + 0x308) == gun->controller &&
            primary_trigger_pointer(gun->controller) == (uintptr_t)LX(0x3b04000), "primary_controller_replaced");
    }
}

static double primary_trigger_time(void) {
    double now = 0;
    primary_trigger_require(gate_read_local(gate_tls_time(gate_tls_self()), &now, 8) && isfinite(now),
                            "primary_time");
    return now;
}

static void *primary_trigger_allocate(unsigned size) {
    void *object = ((void *(*)(size_t, unsigned, unsigned))LX(0x1a448b0))(size, 16, 0);
    primary_trigger_require(object != NULL && !((uintptr_t)object & 15), "primary_allocation");
    return object;
}

/* Stock no-target notification objects, native allocator and native ownership.
 * send() may invoke callbacks; check the retained identity after EACH call. */
static void primary_trigger_notifications(primary_trigger_slot *slot, primary_trigger_gun *gun) {
    unsigned char *event = primary_trigger_allocate(0x20);
    uintptr_t vtable = (uintptr_t)LX(0x3b04130);
    memcpy(event, &vtable, 8);
    memset(event + 8, 0, 4);
    memset(event + 0x10, 0, 0x10);
    ((void (*)(uintptr_t, void *, unsigned, double))LX(0x16c5fe0))(
        gun->item.object, event, 1, primary_trigger_time());
    primary_trigger_verify(slot, gun, 1);
    uintptr_t parent = ((uintptr_t (*)(uintptr_t, unsigned, unsigned, void *))LX(0x189fa50))(
        gun->item.object, 0x23, 0, LX(0x3e06680));
    primary_trigger_verify(slot, gun, 1);
    if (parent) {
        event = primary_trigger_allocate(0x28);
        vtable = (uintptr_t)LX(0x3b04178);
        memcpy(event, &vtable, 8);
        memset(event + 8, 0, 4);
        memset(event + 0x10, 0, 8);
        memcpy(event + 0x18, &gun->item.runtime, 8);
        memset(event + 0x20, 0, 8);
        ((void (*)(uintptr_t, void *, unsigned, double))LX(0x16c5fe0))(
            parent, event, 1, primary_trigger_time());
        primary_trigger_verify(slot, gun, 1);
    }
}

static void primary_trigger_set(primary_trigger_slot *slot, primary_trigger_gun *gun, unsigned want) {
    primary_trigger_verify(slot, gun, 1);
    primary_trigger_require(((unsigned char (*)(uintptr_t, unsigned char))LX(0x110f900))(
        gun->controller, (unsigned char)want) == 1, "primary_set_return");
    primary_trigger_verify(slot, gun, 1);
    unsigned char actual = 2;
    primary_trigger_require(gate_read_local((void *)(gun->controller + 0x91), &actual, 1) && actual == want,
                            "primary_set_readback");
}

static void primary_trigger_lease(primary_trigger_slot *slot, primary_trigger_gun *gun) {
    primary_trigger_verify(slot, gun, 0);
    primary_trigger_require(primary_trigger_pointer(gun->item.object + 0x308) == gun->initial_controller,
                            "primary_initial_controller_changed");
    unsigned char firing = 1;
    uint32_t count = 0, marker = 0, after = 0;
    primary_trigger_require(gate_read_local((void *)(gun->item.object + 0x2fd), &firing, 1) && !firing &&
        gate_read_local((void *)(gun->item.object + 0x40), &count, 4) && count && count < INT32_MAX &&
        gate_read_local((void *)(gun->item.object + 0x44), &marker, 4) && marker == 2, "primary_lease_admission");
    ((void (*)(uintptr_t))LX(0xa238b0))(gun->item.object);
    gun->retained = 1;
    primary_trigger_require(gate_read_local((void *)(gun->item.object + 0x40), &after, 4) && after == count + 1,
                            "primary_retain_readback");
    primary_trigger_verify(slot, gun, 0);
    unsigned char *controller = primary_trigger_allocate(0xa0);
    double first = primary_trigger_time(), second = primary_trigger_time();
    primary_trigger_construct(controller, (uintptr_t)LX(0x3b03ed0), (uintptr_t)LX(0x3b04000), first, second);
    primary_trigger_verify(slot, gun, 0);
    primary_trigger_require(primary_trigger_pointer(gun->item.object + 0x308) == gun->initial_controller,
                            "primary_before_install_changed");
    /* From entry, native install owns the controller, including callbacks. Any
     * uncertain result terminates; never retry or free an installed pointer. */
    gun->controller = (uintptr_t)controller;
    ((void (*)(uintptr_t, void *))LX(0x11339b0))(gun->item.object, controller);
    primary_trigger_verify(slot, gun, 1);
    primary_trigger_set(slot, gun, 1);
    primary_trigger_notifications(slot, gun);
    primary_trigger_set(slot, gun, 0);
}

static int player_primary_trigger_prepare(uint64_t generation, const uint64_t saved[2],
                                          const stock_input_record records[2]) {
    if (!primary_trigger.configured) {
        const char *setting = getenv("X4_DEV_PRIMARY_TRIGGER");
        primary_trigger.configured = 1;
        if (!setting) return 1;
        primary_trigger.human = !strcmp(setting, "human-v1");
        primary_trigger_require((primary_trigger.human || !strcmp(setting, "script-v1")) &&
            (!primary_trigger.human || keyboard_probe_queue.config.primary_fire) && player_dispatch_enabled &&
            player_startup()->version == 1 && player_recurring_end >= player_startup()->apply + 179 &&
            player_recurring_end <= player_startup()->apply + 899 && primary_trigger_pins(), "primary_configure");
        primary_trigger.enabled = 1;
        primary_trigger.applied = player_startup()->apply - 1;
    }
    if (!primary_trigger.enabled) return 1;
    primary_trigger_require(generation == primary_trigger.applied + 1 && !primary_trigger.prepared &&
        records && saved && saved[0] == keyboard_probe_queue.config.saved_ship_ids[0] &&
        saved[1] == keyboard_probe_queue.config.saved_ship_ids[1], "primary_prepare");
    if (primary_trigger.human) {
        /* Both records are immutable and already admitted before either slot callback. */
        for (unsigned slot = 0; slot < 2; ++slot) {
            primary_trigger_require(!(records[slot].flags & STOCK_INPUT_SECONDARY_FIRE) &&
                (!(records[slot].flags & STOCK_INPUT_FIRE) || (records[slot].flags & STOCK_INPUT_ACTIVE)) &&
                (generation != player_recurring_end || !(records[slot].flags & STOCK_INPUT_FIRE)), "primary_record");
        }
        for (unsigned slot = 0; slot < 2; ++slot)
            primary_trigger.wanted[slot] = !!(records[slot].flags & STOCK_INPUT_FIRE);
    }
    primary_trigger.prepared = generation;
    return 1;
}

static void player_primary_trigger_apply(uint64_t generation) {
    if (!primary_trigger.enabled) return;
    primary_trigger_require(primary_trigger_boundary(generation) && primary_trigger.prepared == generation &&
        generation == primary_trigger.applied + 1, "primary_boundary");
    uintptr_t ships[2] = {keyboard_probe_binding.ship, lifecycle_discard_ship};
    primary_trigger_require(ships[0] && ships[1] && ships[0] != ships[1], "primary_slot_identity");
    if (!primary_trigger.leased) {
        /* Stage BOTH groups before any reference/controller side effect. */
        for (unsigned slot = 0; slot < 2; ++slot) {
            primary_trigger_slot *state = &primary_trigger.slots[slot];
            player_weapon_item items[PLAYER_WEAPON_MAX] = {{0}};
            unsigned count = 0;
            player_weapon_reader reader = {player_fire_observation_read, player_fire_observation_resolve,
                                          player_fire_observation_under_ship, NULL};
            state->ship = ships[slot];
            player_fire_observation_resolver_failed = 0;
            primary_trigger_require(primary_trigger_group_read(state->ship, &state->group) &&
                player_weapon_collect(&reader, state->ship, 0, items, &count) && count &&
                !player_fire_observation_resolver_failed, "primary_group_stage");
            state->count = count;
            for (unsigned index = 0; index < count; ++index) state->guns[index].item = items[index];
        }
        /* Preflight every gun on both slots before the first native effect. */
        for (unsigned slot = 0; slot < 2; ++slot) {
            primary_trigger_slot *state = &primary_trigger.slots[slot];
            for (unsigned index = 0; index < state->count; ++index) {
                primary_trigger_gun *gun = &state->guns[index];
                primary_trigger_verify(state, gun, 0);
                unsigned char firing = 1;
                uintptr_t controller = primary_trigger_pointer(gun->item.object + 0x308);
                gun->initial_controller = controller;
                primary_trigger_require(gate_read_local((void *)(gun->item.object + 0x2fd), &firing, 1) && !firing &&
                    (!controller || primary_trigger_pointer(controller) == (uintptr_t)LX(0x3b2fc38)),
                    "primary_initial_controller");
                for (unsigned other_slot = 0; other_slot <= slot; ++other_slot) {
                    unsigned limit = other_slot == slot ? index : primary_trigger.slots[other_slot].count;
                    for (unsigned other = 0; other < limit; ++other) {
                        primary_trigger_require(primary_trigger.slots[other_slot].guns[other].item.runtime != gun->item.runtime &&
                            primary_trigger.slots[other_slot].guns[other].item.object != gun->item.object,
                            "primary_duplicate_gun");
                    }
                }
            }
        }
        for (unsigned slot = 0; slot < 2; ++slot) {
            primary_trigger_slot *state = &primary_trigger.slots[slot];
            for (unsigned index = 0; index < state->count; ++index) primary_trigger_lease(state, &state->guns[index]);
        }
        primary_trigger.leased = 1;
    }
    unsigned want = primary_trigger_script(generation, player_startup()->apply);
    unsigned firing_count[2] = {0, 0};
    for (unsigned slot = 0; slot < 2; ++slot) {
        primary_trigger_slot *state = &primary_trigger.slots[slot];
        primary_trigger_require(state->ship == ships[slot], "primary_ship_changed");
        for (unsigned index = 0; index < state->count; ++index) {
            primary_trigger_gun *gun = &state->guns[index];
            primary_trigger_set(state, gun, primary_trigger.human ? primary_trigger.wanted[slot] : want);
            unsigned char firing = 2;
            primary_trigger_require(gate_read_local((void *)(gun->item.object + 0x2fd), &firing, 1) && firing <= 1,
                                    "primary_firing_readback");
            firing_count[slot] += firing;
        }
    }
    char row[256];
    int length;
    if (primary_trigger.human) length = snprintf(row, sizeof row,
        "X4LAN PRIMARY_HUMAN v=1 tick=%llu worker=%llu want1=%u want2=%u p1=%u p2=%u firing1=%u firing2=%u terminate_only=1\n",
        (unsigned long long)generation, (unsigned long long)GetCurrentThreadId(),
        primary_trigger.wanted[0], primary_trigger.wanted[1], primary_trigger.slots[0].count,
        primary_trigger.slots[1].count, firing_count[0], firing_count[1]);
    else length = snprintf(row, sizeof row,
        "X4LAN PRIMARY_TRIGGER v=1 tick=%llu worker=%llu script=%u p1=%u p2=%u firing1=%u firing2=%u terminate_only=1\n",
        (unsigned long long)generation, (unsigned long long)GetCurrentThreadId(), want,
        primary_trigger.slots[0].count, primary_trigger.slots[1].count, firing_count[0], firing_count[1]);
    primary_trigger_require(length > 0 && (size_t)length < sizeof row && write(2, row, (size_t)length) == length,
                            "primary_receipt");
    primary_trigger.applied = generation;
    primary_trigger.prepared = 0;
}
#endif
