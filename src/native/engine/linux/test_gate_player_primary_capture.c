#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <setjmp.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "player_space_context_vector.h"

typedef struct { const char *name; unsigned va, size; const char *sha; } lx_site;
typedef struct { uintptr_t address, handler; unsigned kind, key; } sko_node;
static sko_node nodes[40], sko_scratch[40];
static unsigned node_count, bad_pin, boundary, worker, focus, blocked, dirty, cas_fail, partial, bad_identity, bad_census, bad_owner;
static _Alignas(8) unsigned char owner_bytes[0xd00], player_bytes[0x8a548];
static uint64_t vector[3];
static struct { uintptr_t owner; } sko_session;
static struct { uint64_t issued; unsigned slot; } stats;
static struct { uint64_t tick; struct { uint64_t first_capture, last_capture; } config; } keyboard_probe_queue;
static unsigned player_dispatch_enabled = 1, stock_observer_main_boundary = 1, main_thread = 1;
static _Atomic unsigned stock_observer_input_depth;
static uintptr_t factory_probe_player1;
static struct { unsigned version; } phases = {1};
#define player_startup() (&phases)
#define LX(va) ((void *)(uintptr_t)(va))
static jmp_buf terminal;
static _Noreturn void fixture_exit(int status) { assert(status == 225); longjmp(terminal, 1); }
#define _exit fixture_exit
static int site_ok(const lx_site *site) { (void)site; return !bad_pin; }
static int stock_observer_pins(void *unused) { (void)unused; return !bad_pin; }
static unsigned GetCurrentThreadId(void) { return 1; }
static int factory_probe_main_boundary(void) { return boundary; }
static int stock_observer_slot_valid(void) { return 1; }
static int keyboard_probe_identity(void) { return !bad_identity; }
static int keyboard_probe_worker(void) { return worker; }
static int stock_observer_worker_boundary(void) { return !atomic_load(&stock_observer_input_depth); }
static int player_cursor_mode(void) { return 1; }
static int player_stock_focus_wanted(void) { return 1; }
static int player_stock_focus_read(uint64_t generation, unsigned *out) {
    if (generation != stats.issued) return 0;
    *out = focus;
    return 1;
}
static int player_space_mode(void) { return 0; }
static int player_space_local_state(unsigned *out) { *out = 1; return 1; }
static int gate_read_local(const void *address, void *out, size_t size) {
    uintptr_t va = (uintptr_t)address;
    if (va == 0x2e25d80) { uint32_t bits = 0x38d1b717; memcpy(out, &bits, size); return 1; }
    if (va == 0x3e5b2a0) { *(unsigned char *)out = blocked; return 1; }
    if (va >= 0x3e00000 && va < 0x3f00000) { *(unsigned char *)out = dirty; return 1; }
    memcpy(out, address, size);
    return 1;
}
static int sko_census(sko_node *out, unsigned *count, uintptr_t *owner) {
    if (bad_census) return 0;
    memcpy(out, nodes, node_count * sizeof *out); *count = node_count;
    *owner = sko_session.owner + (bad_owner ? 8 : 0); return 1;
}
#define SKO_CAS_APPLIED 1
static int stock_observer_swap_node(void *unused, uintptr_t address, uintptr_t expected, uintptr_t replacement);
static int vector_range(void *unused, uintptr_t address, size_t size, unsigned writable) {
    (void)unused; (void)address; (void)size; (void)writable; return 1;
}
static int vector_read(void *unused, uintptr_t address, void *out, size_t size) {
    (void)unused; memcpy(out, (void *)address, size); return 1;
}
static player_space_vector_swap vector_cas(void *unused, uintptr_t address, uint64_t expected, uint64_t replacement) {
    (void)unused; uint64_t *slot = (uint64_t *)address;
    if (*slot != expected) return PLAYER_SPACE_VECTOR_SWAP_REJECTED;
    *slot = replacement; return PLAYER_SPACE_VECTOR_SWAP_APPLIED;
}
static struct { player_space_vector_ops vector; } player_space_ops = {{NULL,vector_range,vector_read,vector_cas}};
#include "gate_player_primary_capture.h"

static int stock_observer_swap_node(void *unused, uintptr_t address, uintptr_t expected, uintptr_t replacement) {
    (void)unused;
    if (partial) primary_capture_dispatch(0,1,0x18,1,(uintptr_t)LX(0x1051074));
    if (cas_fail) return 0;
    for (unsigned index = 0; index < node_count; ++index) {
        if (nodes[index].address + 0x28 == address && nodes[index].handler == expected) {
            nodes[index].handler = replacement; return SKO_CAS_APPLIED;
        }
    }
    return 0;
}

static void setup(void) {
    memset(&player_fire_capture, 0, sizeof player_fire_capture);
    memset(owner_bytes, 0, sizeof owner_bytes);
    memset(player_bytes, 0, sizeof player_bytes);
    node_count = bad_pin = blocked = dirty = cas_fail = partial = bad_identity = 0;
    bad_census = bad_owner = 0;
    boundary = worker = focus = 1;
    atomic_store(&stock_observer_input_depth, 0);
    sko_session.owner = (uintptr_t)owner_bytes;
    factory_probe_player1 = (uintptr_t)player_bytes;
    owner_bytes[0xcf0] = 1;
    vector[0] = 0x1247430; vector[1] = 0x12475f0; vector[2] = 0x1234;
    uint64_t header[] = {(uintptr_t)vector,(uintptr_t)(vector+3),(uintptr_t)(vector+3)};
    memcpy(owner_bytes+0x10, header, sizeof header);
    for (unsigned family = 0; family < 2; ++family) {
        for (unsigned kind = 1; kind <= 2; ++kind) {
            unsigned ids[] = {0x18,0x19,0x30,0x31};
            for (unsigned index = 0; index < 4; ++index) {
                unsigned original = kind == 1 ? (family ? 0x1247460 : 0x1247080) : (family ? 0x1247590 : 0x1247310);
                nodes[node_count] = (sko_node){0x1000+node_count*0x40,original,kind,kind == 1 ? ids[index] : 0x11+index};
                ++node_count;
            }
        }
    }
    stats.issued = keyboard_probe_queue.tick = 38; stats.slot = 1;
    keyboard_probe_queue.config.first_capture = 38; keyboard_probe_queue.config.last_capture = 217;
    unsetenv("X4_DEV_PRIMARY_TRIGGER"); setenv("X4_DEV_PRIMARY_CAPTURE","capture-v1",1);
    assert(player_primary_capture_request(1));
}

static void installed(void) { setup(); assert(player_primary_capture_admit(38)); atomic_store(&stock_observer_input_depth,1); }
static void event(unsigned family, unsigned kind, unsigned id, uint32_t raw) {
    errno = EDOM;
    primary_capture_dispatch(family,kind,id,raw,(uintptr_t)LX(kind == 1 ? 0x1051074 : 0xced008));
    assert(errno == EDOM);
}
#define REFUSES(expression) do { if (!setjmp(terminal)) { expression; assert(!"expected terminal refusal"); } ++refusals; } while (0)

int main(void) {
    unsigned refusals = 0;
    setup(); unsetenv("X4_DEV_PRIMARY_CAPTURE"); memset(&player_fire_capture,0,sizeof player_fire_capture);
    assert(player_primary_capture_request(1) && player_primary_capture_admit(38));
    assert(nodes[0].handler == 0x1247080 && !player_fire_capture.installed);
    setup(); memset(&player_fire_capture,0,sizeof player_fire_capture);
    setenv("X4_DEV_PRIMARY_TRIGGER", "human-v1", 1);
    assert(player_primary_capture_request(1));
    setup(); memset(&player_fire_capture,0,sizeof player_fire_capture);
    setenv("X4_DEV_PRIMARY_TRIGGER", "script-v1", 1);
    assert(!player_primary_capture_request(1));
    installed(); event(0,1,0x18,1); event(1,1,0x18,1); event(0,1,0x18,0);
    assert(primary_capture_held(&player_fire_capture.state));
    focus=0; event(1,1,0x18,1); focus=1; event(1,1,0x18,1);
    assert(!primary_capture_held(&player_fire_capture.state));
    event(1,1,0x18,0); event(1,1,0x18,1); assert(primary_capture_held(&player_fire_capture.state));
    errno=EDOM; primary_capture_context0(8); assert(errno==EDOM);
    event(1,1,0x18,1); assert(!primary_capture_held(&player_fire_capture.state));
    event(1,1,0x18,0); event(1,1,0x18,1); assert(primary_capture_held(&player_fire_capture.state));
    primary_capture_context1(7); event(0,1,0x19,1);
    assert(primary_capture_held(&player_fire_capture.state));
    event(1,1,0x18,0); event(0,2,0x11,0x38d1b716); assert(!primary_capture_held(&player_fire_capture.state));
    event(0,2,0x11,0x38d1b717); assert(primary_capture_held(&player_fire_capture.state));
    event(0,2,0x11,0); atomic_store(&stock_observer_input_depth,0);
    unsigned held = 2;
    assert(!player_primary_capture_sample(38, &held));
    assert(player_primary_capture_seal(38));
    assert(player_primary_capture_sample(38, &held) && held == 0);
    assert(player_primary_capture_sample(38, &held) && held == 0);
    assert(!player_primary_capture_sample(39, &held));
    atomic_store(&player_fire_capture.busy,1);
    assert(!player_primary_capture_sample(38, &held));
    assert(atomic_load(&player_fire_capture.busy) == 1);
    atomic_store(&player_fire_capture.busy,0);
    primary_capture_context0(8);
    assert(!player_primary_capture_sample(38, &held));
    REFUSES(player_primary_capture_seal(38));
    installed(); focus=0; atomic_store(&stock_observer_input_depth,0); assert(player_primary_capture_seal(38));
    stats.issued=keyboard_probe_queue.tick=39; assert(player_primary_capture_admit(39));
    focus=1; atomic_store(&stock_observer_input_depth,1); event(0,1,0x18,1); assert(!primary_capture_held(&player_fire_capture.state));
    /* A gate change without an input callback must invalidate the sealed sample. */
    installed(); event(0,1,0x18,1); assert(primary_capture_held(&player_fire_capture.state));
    blocked=1;
    atomic_store(&stock_observer_input_depth,0);
    assert(player_primary_capture_seal(38));
    assert(player_primary_capture_sample(38, &held) && held == 0);
    blocked=0; stats.issued=keyboard_probe_queue.tick=39;
    assert(player_primary_capture_admit(39));
    atomic_store(&stock_observer_input_depth,1);
    event(0,1,0x18,1); assert(!primary_capture_held(&player_fire_capture.state));
    atomic_store(&stock_observer_input_depth,0);
    assert(player_primary_capture_seal(39));
    assert(player_primary_capture_sample(39, &held) && held == 0);
    stats.issued=keyboard_probe_queue.tick=40; assert(player_primary_capture_admit(40));
    atomic_store(&stock_observer_input_depth,1);
    event(0,1,0x18,0); event(0,1,0x18,1);
    atomic_store(&stock_observer_input_depth,0);
    assert(player_primary_capture_seal(40));
    assert(player_primary_capture_sample(40, &held) && held == 1);
    installed(); event(0,1,0x18,1); blocked=1; event(0,1,0x18,1);
    blocked=0; event(0,1,0x18,1); assert(!primary_capture_held(&player_fire_capture.state));
    event(0,1,0x18,0); event(0,1,0x18,1); assert(primary_capture_held(&player_fire_capture.state));
    owner_bytes[0xcf0]=0; event(0,1,0x18,1); owner_bytes[0xcf0]=1; event(0,1,0x18,1);
    assert(!primary_capture_held(&player_fire_capture.state));
    installed(); atomic_store(&stock_observer_input_depth,0); stats.issued=keyboard_probe_queue.tick=39;
    REFUSES(player_primary_capture_admit(39));
    installed(); blocked=2; atomic_store(&stock_observer_input_depth,0); REFUSES(player_primary_capture_seal(38));
    installed(); worker=0; REFUSES(event(0,1,0x18,1));
    installed(); REFUSES(event(0,1,0x18,2));
    installed(); REFUSES(event(0,2,0x11,0x7fc00000));
    installed(); REFUSES(primary_capture_dispatch(0,1,0x18,1,0));
    installed(); atomic_store(&player_fire_capture.busy,1); REFUSES(primary_capture_context0(8));
    installed(); REFUSES(event(0,1,0x17,1));
    installed(); for(unsigned index=0;index<128;++index) event(0,1,0x18,0); REFUSES(event(0,1,0x18,0));
    setup(); bad_census=1; REFUSES(player_primary_capture_admit(38));
    setup(); bad_owner=1; REFUSES(player_primary_capture_admit(38));
    setup();
    for (unsigned index = 16; index < 40; ++index) {
        nodes[index] = nodes[0]; nodes[index].address = 0x1000 + index * 0x40;
    }
    node_count=40; nodes[0].handler=0xabcdef;
    REFUSES(player_primary_capture_admit(38));
    setup(); nodes[1]=nodes[0]; REFUSES(player_primary_capture_admit(38));
    setup(); nodes[0].handler=0x1111; REFUSES(player_primary_capture_admit(38));
    setup(); --node_count; REFUSES(player_primary_capture_admit(38));
    setup(); boundary=0; REFUSES(player_primary_capture_admit(38));
    setup(); bad_pin=1; REFUSES(player_primary_capture_admit(38));
    setup(); dirty=1; REFUSES(player_primary_capture_admit(38));
    setup(); cas_fail=1; REFUSES(player_primary_capture_admit(38));
    setup(); partial=1; REFUSES(player_primary_capture_admit(38));
    installed(); nodes[0].handler=0x1111; atomic_store(&stock_observer_input_depth,0); REFUSES(player_primary_capture_seal(38));
    installed(); vector[0]=0x1111; atomic_store(&stock_observer_input_depth,0); REFUSES(player_primary_capture_seal(38));
    installed(); bad_identity=1; REFUSES(event(0,1,0x18,1));
    printf("primary capture actual adapter: %u terminal refusals; focus/rearm/families/context/threshold/default-off PASS\n", refusals);
    return 0;
}
