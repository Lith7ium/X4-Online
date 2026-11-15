#define _GNU_SOURCE
#include <assert.h>
#include <limits.h>
#include <math.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "player_weapon_groups.h"

typedef struct { const char *name; unsigned va, size; const char *sha; } lx_site;
#define STOCK_INPUT_ACTIVE 1u
#define STOCK_INPUT_FIRE 16u
#define STOCK_INPUT_SECONDARY_FIRE 32u
typedef struct { unsigned flags; } stock_input_record;
static struct { uint64_t issued; } stats;
static struct { uint64_t generation; } player_recurring_tail_token;
static struct { struct { uint64_t saved_ship_ids[2]; unsigned primary_fire; } config; } keyboard_probe_queue;
static struct { uintptr_t ship; } keyboard_probe_binding;
static struct { unsigned version; uint64_t apply; } phases = {1,40};
static unsigned player_dispatch_enabled = 1, player_network_busy, player_physics_replay_busy;
static uint64_t player_recurring_end = 219, player_dispatch_ticket;
static unsigned player_dispatch;
#define PWDA_JOINED 1u
static unsigned pwda_phase(const unsigned *adapter) { (void)adapter; return 1; }
static uintptr_t lifecycle_discard_ship;
static unsigned char ships[2][0x660], guns[2][0x320];
static uint64_t ids[2][1];
static uintptr_t groups[2][3];
static double now = 1.25;
static unsigned calls, sends, retains, alloc_fail, replace_on_send, bad_worker, bad_retain, pin_bad, replace_next, replace_allocate, die_on_send;
static int player_fire_observation_resolver_failed;
static jmp_buf rejected;
static const char *failure;

static void lifecycle_discard_require(int condition, const char *reason) {
    if (!condition) { failure = reason; longjmp(rejected, 1); }
}
static int site_ok(const lx_site *site) { (void)site; return !pin_bad; }
static int player_target_hold_pins(void) { return !pin_bad; }
static void *gate_tls_self(void) { return &now; }
static void *gate_tls_time(void *tls) { return tls; }
static int gate_tls_worker(void *tls) { (void)tls; return !bad_worker; }
static int player_recurring_physics_entered(void) { return !bad_worker; }
static int keyboard_probe_identity(void) { return 1; }
static int player_physics_identity(void) { return 1; }
static unsigned GetCurrentThreadId(void) { return 77; }
#define player_startup() (&phases)
static void *address(unsigned va);
static int gate_read_local(const void *address, void *out, size_t size) {
    if (!address) return 0;
    static const unsigned slots[][2] = {
        {0x3c6c628,0x18a7df0}, {0x3b04028,0x1271060}, {0x3b04078,0x110f8e0},
        {0x3b040a8,0x1089ed0}, {0x3b040c0,0x124ed60}, {0x3b040d0,0x124ee80},
        {0x3b040d8,0x1254080}, {0x3b04100,0x110f900},
    };
    for (unsigned index=0;index<sizeof slots/sizeof slots[0];++index) {
        if ((uintptr_t)address==slots[index][0]) {
            extern void *fixture_target(unsigned);
            uintptr_t target=(uintptr_t)fixture_target(slots[index][1]);
            assert(size==8);memcpy(out,&target,8);return 1;
        }
    }
    memcpy(out,address,size); return 1;
}
static int player_fire_observation_read(void *context, uintptr_t address, void *out, size_t size) {
    (void)context; return gate_read_local((void *)address,out,size);
}
static uintptr_t player_fire_observation_resolve(void *context, uint64_t runtime) {
    (void)context;
    for (unsigned slot=0; slot<2; ++slot) if (runtime==ids[slot][0]) return (uintptr_t)guns[slot];
    return 0;
}
static int player_fire_observation_under_ship(void *context, uintptr_t gun, uintptr_t ship) {
    (void)context;
    return (gun==(uintptr_t)guns[0] && ship==(uintptr_t)ships[0]) ||
           (gun==(uintptr_t)guns[1] && ship==(uintptr_t)ships[1]);
}
static void *allocate(size_t size, unsigned alignment, unsigned tag) {
    assert(alignment==16 && !tag); ++calls;
    if (alloc_fail) return NULL;
    if (replace_allocate && size == 0xa0) { uintptr_t other=1; memcpy(guns[0]+0x308,&other,8); }
    void *result=NULL; assert(!posix_memalign(&result,16,size)); memset(result,0xcc,size); return result;
}
static void acquire(uintptr_t gun) {
    ++calls; ++retains;
    if (!bad_retain) { uint32_t count; memcpy(&count,(void *)(gun+0x40),4); ++count; memcpy((void *)(gun+0x40),&count,4); }
}
static void install(uintptr_t gun, void *controller) {
    ++calls; memcpy((void *)(gun+0x308),&controller,8);
    if (replace_next==1 && gun==(uintptr_t)guns[0]) {
        uintptr_t other=1;memcpy(guns[1]+0x308,&other,8);
    }
}
static unsigned char set_trigger(uintptr_t controller, unsigned char want) {
    ++calls; ((unsigned char *)controller)[0x91]=want; return 1;
}
static uintptr_t parent(uintptr_t gun, unsigned type, unsigned option, void *token) {
    (void)gun; (void)token; assert(type==0x23 && !option); return (uintptr_t)ships[0];
}
static void send_event(uintptr_t recipient, void *event, unsigned immediate, double time) {
    (void)recipient; assert(immediate==1 && time==now); ++calls; ++sends;
    if (replace_on_send) { uintptr_t zero=0; memcpy(guns[0]+0x308,&zero,8); }
    if (die_on_send) guns[0][0xd1]=0;
    if (replace_next==2) { uintptr_t other=1;memcpy(guns[1]+0x308,&other,8); }
    free(event);
}
static void *address(unsigned va) {
    switch (va) {
    case 0x1a448b0:return allocate;
    case 0xa238b0:return acquire;
    case 0x11339b0:return install;
    case 0x110f900:return set_trigger;
    case 0x189fa50:return parent;
    case 0x16c5fe0:return send_event;
    default:return (void *)(uintptr_t)va;
    }
}
void *fixture_target(unsigned va) { return address(va); }
#define LX(va) address(va)
#include "gate_player_primary_trigger.h"

static void reset(void) {
    memset(&primary_trigger,0,sizeof primary_trigger);
    memset(ships,0,sizeof ships); memset(guns,0,sizeof guns);
    calls=sends=retains=alloc_fail=replace_on_send=bad_worker=bad_retain=pin_bad=0;
    replace_next=replace_allocate=die_on_send=0;
    failure=NULL; player_network_busy=player_physics_replay_busy=0; player_dispatch_enabled=1;
    stats.issued=player_recurring_tail_token.generation=player_dispatch_ticket=40;
    keyboard_probe_binding.ship=(uintptr_t)ships[0]; lifecycle_discard_ship=(uintptr_t)ships[1];
    keyboard_probe_queue.config.saved_ship_ids[0]=10; keyboard_probe_queue.config.saved_ship_ids[1]=20;
    for (unsigned slot=0;slot<2;++slot) {
        guns[slot][0xd1]=1;
        ids[slot][0]=100+slot;
        groups[slot][0]=(uintptr_t)ids[slot];groups[slot][1]=(uintptr_t)(ids[slot]+1);
        uintptr_t bounds[2]={(uintptr_t)groups[slot],(uintptr_t)(groups[slot]+3)};
        memcpy(ships[slot]+0x628,bounds,16);
        uintptr_t ref=0x3c6c628;memcpy(guns[slot]+0x38,&ref,8);
        uint32_t value=2;memcpy(guns[slot]+0x40,&value,4);memcpy(guns[slot]+0x44,&value,4);
    }
    setenv("X4_DEV_PRIMARY_TRIGGER","script-v1",1);
}
static void tick(uint64_t generation) {
    stock_input_record records[2]={{0},{0}};
    stats.issued=player_recurring_tail_token.generation=player_dispatch_ticket=generation;
    assert(player_primary_trigger_prepare(generation,keyboard_probe_queue.config.saved_ship_ids,records));
    player_primary_trigger_apply(generation);
}
static void negative(unsigned variant) {
    reset();
    if (setjmp(rejected)) {
        assert(failure);
        if (variant==0 || variant==1 || variant==5 || variant==6 || variant==16 || variant==17) assert(!calls);
        return;
    }
    if (variant==0) { bad_worker=1;tick(40); }
    if (variant==1) { pin_bad=1;tick(40); }
    if (variant==2) { alloc_fail=1;tick(40); }
    if (variant==3) { bad_retain=1;tick(40); }
    if (variant==4) { replace_on_send=1;tick(40); }
    if (variant==5) { memset(ships[1]+0x628,0,16);tick(40); }
    if (variant==6) { guns[1][0x2fd]=1;tick(40); }
    if (variant==13) { replace_next=1;tick(40); }
    if (variant==14) { replace_next=2;tick(40); }
    if (variant==15) { replace_allocate=1;tick(40); }
    if (variant==16) { guns[1][0xd1]=0;tick(40); }
    if (variant==17) { guns[1][0x68]=1;tick(40); }
    if (variant==18) { tick(40);guns[0][0xd1]=0;tick(41); }
    if (variant==19) { die_on_send=1;tick(40); }
    if (variant>=7 && variant<=12) {
        tick(40);
        if (variant==7) tick(40);
        if (variant==8) tick(42);
        if (variant==9) { uintptr_t zero=0;memcpy(guns[0]+0x308,&zero,8);tick(41); }
        if (variant==10) { ids[1][0]=777;tick(41); }
        if (variant==11) { bad_worker=1;tick(41); }
        if (variant==12) { player_network_busy=1;tick(41); }
    }
    assert(!"negative case admitted");
}
int main(void) {
    reset();
    unsigned char object[0xa0];memset(object,0xcc,sizeof object);
    primary_trigger_construct(object,1,2,1.25,1.25);
    assert(object[0x91]==0 && object[0x90]==0 && object[0x92]==0xcc && object[0x58]==0xcc);
    if (setjmp(rejected)) { fprintf(stderr,"unexpected %s\n",failure);return 1; }
    unsigned burst=0;
    for (unsigned generation=40;generation<220;++generation) {
        tick(generation);burst+=primary_trigger_script(generation,40);
    }
    assert(burst==6 && retains==2 && sends==4 && primary_trigger.applied==219);
    /* Both owned triggers are neutral; ownership stays resident until exit. */
    for (unsigned slot=0;slot<2;++slot) assert(!((unsigned char *)primary_trigger.slots[slot].guns[0].controller)[0x91]);
    for (unsigned variant=0;variant<20;++variant) negative(variant);
    reset();setenv("X4_DEV_PRIMARY_TRIGGER", "human-v1", 1);
    keyboard_probe_queue.config.primary_fire = 1;
    for (uint64_t generation = 40; generation < 220; ++generation) {
        stock_input_record records[2] = {{STOCK_INPUT_ACTIVE}, {STOCK_INPUT_ACTIVE}};
        unsigned want1 = generation >= 44 && generation < 49;
        unsigned want2 = generation >= 47 && generation < 53;
        if (want1) records[0].flags |= STOCK_INPUT_FIRE;
        if (want2) records[1].flags |= STOCK_INPUT_FIRE;
        stats.issued = player_recurring_tail_token.generation = player_dispatch_ticket = generation;
        assert(player_primary_trigger_prepare(generation, keyboard_probe_queue.config.saved_ship_ids, records));
        player_primary_trigger_apply(generation);
        for (unsigned slot = 0; slot < 2; ++slot)
            assert(((unsigned char *)primary_trigger.slots[slot].guns[0].controller)[0x91] == (slot ? want2 : want1));
    }
    /* Reject an invalid second record before leasing either gun. */
    reset();setenv("X4_DEV_PRIMARY_TRIGGER", "human-v1", 1);keyboard_probe_queue.config.primary_fire = 1;
    if (!setjmp(rejected)) {
        stock_input_record records[2] = {{STOCK_INPUT_ACTIVE | STOCK_INPUT_FIRE}, {STOCK_INPUT_SECONDARY_FIRE}};
        player_primary_trigger_prepare(40, keyboard_probe_queue.config.saved_ship_ids, records);
        assert(!"secondary admitted");
    }
    assert(!calls && !strcmp(failure, "primary_record"));
    reset();unsetenv("X4_DEV_PRIMARY_TRIGGER");tick(40);assert(!calls && !primary_trigger.enabled);
    /* Disabled admission is immutable even if an environment variable appears later. */
    setenv("X4_DEV_PRIMARY_TRIGGER","script-v1",1);tick(41);assert(!calls);
    puts("primary trigger: constructor, 180 generations, 20 refusals, immutable off PASS");
    return 0;
}
