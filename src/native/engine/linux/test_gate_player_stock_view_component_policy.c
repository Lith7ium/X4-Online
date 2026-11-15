#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include "player_stock_view_state.h"
static uintptr_t registry_global;
static uintptr_t test_address(uintptr_t address) {
    return address == 0x3daa860 ? (uintptr_t)&registry_global : address;
}
#define LX(address) test_address(address)
#define SEAT_PREFLIGHT_SHIP_VTABLE 0x3d21748
static struct { uint64_t issued; } stats;
static struct { uintptr_t ship; } factory_probe_identity;
static uintptr_t lifecycle_discard_ship;
static uintptr_t stock_view_gate_ships[2], stock_view_gate_controllers[2];
static player_stock_view_state stock_view_gate_state;
static int owner_valid;
static unsigned read_calls, fail_read, mutate_read;
static uintptr_t mutate_address;
static uint64_t mutate_value;
static int read_local(void *address, void *out, unsigned size) {
    ++read_calls;
    if (fail_read == read_calls) return 0;
    if (mutate_read == read_calls) memcpy((void *)mutate_address, &mutate_value, 8);
    memcpy(out, address, size);
    return 1;
}
static char captured_receipt[4096];
static size_t captured_size;
static unsigned write_calls, interrupted_writes, partial_writes;
static ssize_t capture_write(int descriptor, const void *bytes, size_t size) {
    assert(descriptor == STDERR_FILENO);
    ++write_calls;
    if (interrupted_writes) { --interrupted_writes; errno = EINTR; return -1; }
    if (partial_writes) { --partial_writes; size = 7; }
    assert(captured_size + size < sizeof captured_receipt);
    memcpy(captured_receipt + captured_size, bytes, size);
    captured_size += size;
    captured_receipt[captured_size] = 0;
    errno = EIO;
    return (ssize_t)size;
}
#define write capture_write
static int stock_view_gate_owner(uintptr_t controller, unsigned *slot) {
    if (!owner_valid || stats.issued != stock_view_gate_state.generation) return 0;
    *slot = controller == stock_view_gate_controllers[0] ? 1 : controller == stock_view_gate_controllers[1] ? 2 : 0;
    return 1;
}
#include "gate_player_stock_view_component_policy.h"
#undef write
typedef struct { uintptr_t class_pointer; uint64_t runtime; unsigned char padding[0x60]; uintptr_t parent; } component;
int main(void) {
    stats.issued = 42; owner_valid = 1;
    stock_view_gate_ships[0] = factory_probe_identity.ship = 0x1000;
    stock_view_gate_ships[1] = lifecycle_discard_ship = 0x2000;
    stock_view_gate_controllers[0] = 0x3000; stock_view_gate_controllers[1] = 0x4000;
    stock_view_gate_state = (player_stock_view_state){.generation = 42, .saved = {11, 22}, .initialized = 1,
        .slots = {{.cockpit = 1, .floating = 0}, {.cockpit = 0, .floating = 1}}};
    component object = {0x3c6a440, 1, {0}, 0x2000};
    unsigned char result = 0;
    assert(stock_view_component_gate_policy(0, (uintptr_t)&object, 0xa5, &result) && result == 1);
    object.class_pointer = 0x3ccad80;
    uintptr_t result_pointer = 0;
    assert(stock_view_precompare_gate_policy((uintptr_t)&object, 0x2000, 0x1000, &result_pointer) &&
           result_pointer == 0x2000);
    assert(!stock_view_precompare_gate_policy((uintptr_t)&object, 0x1000, 0x1000, &result_pointer));
    assert(!stock_view_precompare_gate_policy((uintptr_t)&object, 0x2000, 0x9000, &result_pointer));
    owner_valid = 0;
    assert(!stock_view_precompare_gate_policy((uintptr_t)&object, 0x2000, 0x1000, &result_pointer));
    object.class_pointer = 0x3c6a440;
    assert(!stock_view_component_gate_policy(0, (uintptr_t)&object, 0xa5, &result));
    unsigned char registry[0x68] = {0}, block[32] = {0};
    uintptr_t block_address = (uintptr_t)block;
    registry_global = (uintptr_t)registry;
    memcpy(registry + 0x60, &block_address, 8);
    component foreign_ship = {SEAT_PREFLIGHT_SHIP_VTABLE, 2, {0}, 0};
    uintptr_t component_address = (uintptr_t)&object, ship_address = (uintptr_t)&foreign_ship;
    memcpy(block, &component_address, 8);
    memcpy(block + 8, &ship_address, 8);
    uint32_t flags = (5u << 16) | (5u << 20);
    memcpy(block + 28, &flags, 4);
    object.parent = ship_address;
    assert(stock_view_component_gate_policy(0, component_address, 0xa5, &result) && result == 0xa5);
    object.class_pointer = 0x3ccad80;
    assert(stock_view_precompare_gate_policy(component_address, ship_address, 0xabcdef, &result_pointer) &&
           result_pointer == 0xabcdef);
    assert(!stock_view_precompare_gate_policy(component_address, 0x2000, 0xabcdef, &result_pointer));
    object.class_pointer = 0x3c6a440;
    foreign_ship.class_pointer = 0xdead;
    assert(!stock_view_component_gate_policy(0, component_address, 0xa5, &result));
    foreign_ship.class_pointer = SEAT_PREFLIGHT_SHIP_VTABLE; foreign_ship.runtime = 0;
    assert(!stock_view_component_gate_policy(0, component_address, 0xa5, &result));
    foreign_ship.runtime = 2; flags = 0;
    memcpy(block + 28, &flags, 4);
    assert(!stock_view_component_gate_policy(0, component_address, 0xa5, &result));
    component intermediate = {0x3c6a440, 66, {0}, 0x2000};
    object.parent = (uintptr_t)&intermediate;
    assert(!stock_view_component_gate_policy(0, (uintptr_t)&object, 0xa5, &result));
    object.parent = 0x2000; owner_valid = 1; stats.issued = 43;
    assert(!stock_view_component_gate_policy(0, (uintptr_t)&object, 0xa5, &result));
    object.class_pointer = 0x3ccad80;
    assert(!stock_view_precompare_gate_policy((uintptr_t)&object, 0x2000, 0x1000, &result_pointer));
    object.class_pointer = 0x3c6a440;
    stats.issued = 42; lifecycle_discard_ship = 0x9000;
    assert(!stock_view_component_gate_policy(0, (uintptr_t)&object, 0xa5, &result));
    /* Receipts must not add engine reads or change failure output sentinels. */
    lifecycle_discard_ship = 0x2000; owner_valid = 1;
    object.class_pointer = 0x3ccad80; object.parent = 0x2000;
    player_stock_view_component_context baseline = stock_view_component_gate_context(NULL);
    read_calls = write_calls = 0; captured_size = 0;
    assert(player_stock_view_precompare_route(&baseline, (uintptr_t)&object, 0x2000, 0x1000, &result_pointer));
    unsigned baseline_reads = read_calls;
    assert(baseline_reads == 4 && result_pointer == 0x2000);
    read_calls = 0;
    assert(stock_view_precompare_gate_policy((uintptr_t)&object, 0x2000, 0x1000, &result_pointer));
    assert(read_calls == baseline_reads && write_calls == 0);

    read_calls = 0; result_pointer = 0x12345678;
    assert(!player_stock_view_precompare_route(&baseline, (uintptr_t)&object, 0x2000, 0x9000, &result_pointer));
    baseline_reads = read_calls;
    assert(baseline_reads == 4 && result_pointer == 0x12345678);
    read_calls = 0; errno = ERANGE; interrupted_writes = partial_writes = 1;
    assert(!stock_view_precompare_gate_policy((uintptr_t)&object, 0x2000, 0x9000, &result_pointer));
    assert(read_calls == baseline_reads && result_pointer == 0x12345678 && errno == ERANGE);
    assert(write_calls == 3 && captured_size < 512 && captured_receipt[captured_size - 1] == '\n');
    assert(strstr(captured_receipt, "policy=precompare reason=original_not_owned"));
    assert(strstr(captured_receipt, " original=0000000000009000 ship1=0000000000001000 ship2=0000000000002000"));

    captured_size = write_calls = read_calls = 0; interrupted_writes = 9;
    assert(!stock_view_precompare_gate_policy((uintptr_t)&object, 0x1000, 0x1000, &result_pointer));
    assert(write_calls == 4 && captured_size == 0 && read_calls == 4 && errno == ERANGE);
    interrupted_writes = 0;
    captured_size = write_calls = read_calls = 0; owner_valid = 0;
    assert(!stock_view_precompare_gate_policy((uintptr_t)&object, 0x2000, 0x1000, &result_pointer));
    assert(read_calls == 2 && result_pointer == 0x12345678);
    assert(strstr(captured_receipt, "reason=owner_authentication"));

    captured_size = write_calls = read_calls = 0;
    object.class_pointer = 0x3c6a440; object.parent = ship_address;
    foreign_ship.class_pointer = 0xdead; result = 0x5a;
    assert(!stock_view_component_gate_policy(0, component_address, 0xa5, &result));
    assert(read_calls == 3 && result == 0x5a);
    assert(strstr(captured_receipt, "reason=foreign_parent_identity"));
    assert(strstr(captured_receipt, " parent_class=000000000000dead parent_runtime=0000000000000002"));
    captured_size = write_calls = read_calls = 0;
    foreign_ship.class_pointer = SEAT_PREFLIGHT_SHIP_VTABLE;
    assert(!stock_view_component_gate_policy(0, component_address, 0xa5, &result));
    assert(read_calls == 6 && result == 0x5a);
    assert(strstr(captured_receipt, "reason=foreign_component_registry"));
    flags = (5u << 16) | (5u << 20); memcpy(block + 28, &flags, 4);
    captured_size = write_calls = read_calls = 0;
    assert(stock_view_component_gate_policy(0, component_address, 0xa5, &result));
    assert(read_calls == 22 && result == 0xa5 && write_calls == 0);
    /* An exact XS foreign parent follows the stock route, even when the
     * getter returns owned ship1. It must never be attributed to that slot. */
    foreign_ship.class_pointer = STOCK_VIEW_COMPONENT_FOREIGN_XS_VTABLE;
    object.class_pointer = 0x3ccad80;
    result_pointer = 0x5555;
    assert(stock_view_precompare_gate_policy(component_address, ship_address, 0x1000, &result_pointer));
    assert(result_pointer == 0x1000);
    result = 0;
    assert(stock_view_component_gate_policy(1, component_address, 0xa5, &result) && result == 0xa5);
    result_pointer = 0x5555;
    assert(!stock_view_precompare_gate_policy(component_address, 0x2000, 0x1000, &result_pointer));
    assert(result_pointer == 0x5555);

    foreign_ship.class_pointer = STOCK_VIEW_COMPONENT_FOREIGN_XS_VTABLE + 8;
    assert(!stock_view_precompare_gate_policy(component_address, ship_address, 0x1000, &result_pointer));
    foreign_ship.class_pointer = STOCK_VIEW_COMPONENT_FOREIGN_XS_VTABLE;
    foreign_ship.runtime = 0;
    assert(!stock_view_precompare_gate_policy(component_address, ship_address, 0x1000, &result_pointer));
    foreign_ship.runtime = 2;

    /* A genuine class alone cannot replace either raw registry identity. */
    uintptr_t absent = 0;
    memcpy(block, &absent, 8);
    assert(!stock_view_precompare_gate_policy(component_address, ship_address, 0x1000, &result_pointer));
    memcpy(block, &component_address, 8);
    memcpy(block + 8, &absent, 8);
    assert(!stock_view_precompare_gate_policy(component_address, ship_address, 0x1000, &result_pointer));
    memcpy(block + 8, &ship_address, 8);
    object.runtime = 0;
    assert(!stock_view_precompare_gate_policy(component_address, ship_address, 0x1000, &result_pointer));
    object.runtime = 1;

    /* Mutate only at the final readbacks, after both registry checks passed. */
    mutate_read = 20;
    mutate_address = (uintptr_t)&foreign_ship.class_pointer;
    mutate_value = SEAT_PREFLIGHT_SHIP_VTABLE;
    read_calls = captured_size = write_calls = 0;
    assert(!stock_view_precompare_gate_policy(component_address, ship_address, 0x1000, &result_pointer));
    assert(strstr(captured_receipt, "reason=foreign_parent_changed"));
    foreign_ship.class_pointer = STOCK_VIEW_COMPONENT_FOREIGN_XS_VTABLE;
    mutate_read = 22;
    mutate_address = (uintptr_t)&object.parent;
    mutate_value = 0x2000;
    read_calls = captured_size = write_calls = 0;
    assert(!stock_view_precompare_gate_policy(component_address, ship_address, 0x1000, &result_pointer));
    assert(strstr(captured_receipt, "reason=identity_readback"));
    object.parent = ship_address;
    mutate_read = 0;
    assert(result_pointer == 0x5555);
    assert(stock_view_precompare_gate_policy(component_address, ship_address, 0x1000, &result_pointer));
    assert(result_pointer == 0x1000);
    return 0;
}
