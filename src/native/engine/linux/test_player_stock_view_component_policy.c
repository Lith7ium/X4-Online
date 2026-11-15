#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "player_stock_view_component_policy.h"

typedef struct {
    uintptr_t class_pointer;
    uint64_t runtime;
    unsigned char padding[0x60];
    uintptr_t parent;
} component_fixture;
typedef struct {
    component_fixture component;
    uint64_t generation;
    unsigned owner, calls, fail_read, drift, foreign_ship_valid;
} fixture;
static int read_component(void *context, uintptr_t address, void *out, unsigned size) {
    fixture *test = context;
    ++test->calls;
    if (test->fail_read == test->calls) return 0;
    if (test->drift && test->calls == 3) ++test->component.runtime;
    memcpy(out, (void *)address, size);
    return 1;
}
static int authenticate(void *context, unsigned slot, uint64_t *generation) {
    fixture *test = context;
    if (!test->owner || slot < 1 || slot > 2) return 0;
    *generation = test->generation;
    return 1;
}
static int foreign_identity(void *context, uintptr_t component, uint64_t runtime, uintptr_t parent) {
    fixture *test = context;
    return component == (uintptr_t)&test->component && runtime == 99 && parent == 0x3000 &&
        test->foreign_ship_valid;
}
int main(void) {
    fixture test = {.component = {0x101, 99, {0}, 0x1000}, .generation = 42, .owner = 1};
    player_stock_view_state state = {.generation = 42, .saved = {11, 22}, .initialized = 1,
        .slots = {{.cockpit = 1, .floating = 1}, {.cockpit = 0, .floating = 0}}};
    player_stock_view_component_context context = {.context = &test, .read = read_component,
        .authenticate = authenticate, .foreign_identity = foreign_identity, .ships = {0x1000, 0x2000}, .classes = {0x101, 0x202}, .state = &state};
    unsigned char result = 0;
    assert(player_stock_view_component_route(&context, 0, (uintptr_t)&test.component, 0xa5, &result) && result == 1);
    test.calls = 0; test.component.parent = 0x2000;
    assert(player_stock_view_component_route(&context, 0, (uintptr_t)&test.component, 0xa5, &result) && result == 0);
    test.calls = 0; test.component.class_pointer = 0x202;
    assert(player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result) && result == 1);
    test.calls = 0; test.component.parent = 0x1000;
    assert(player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result) && result == 0);
    test.calls = 0; test.component.parent = 0x3000; test.owner = 0; test.foreign_ship_valid = 1;
    assert(player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result) && result == 0xa5);
    test.calls = 0; test.component.class_pointer = 0xdead;
    assert(!player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result));
    test.calls = 0; test.component.class_pointer = 0x202; test.component.runtime = 0;
    assert(!player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result));
    test.calls = 0; test.component.runtime = 99; test.foreign_ship_valid = 0;
    assert(!player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result));
    test.calls = 0; test.component.parent = 0x1000;
    assert(!player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result));
    test.calls = 0; test.owner = 1; test.component.class_pointer = 0xdead;
    assert(!player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result));
    test.calls = 0; test.component.class_pointer = 0x202; test.component.runtime = 0;
    assert(!player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result));
    test.calls = 0; test.component.runtime = 99; test.generation = 43;
    assert(!player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result));
    test.calls = 0; test.generation = 42; test.drift = 1;
    assert(!player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result));
    test.calls = 0; test.drift = 0; test.fail_read = 2;
    assert(!player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result));
    /* Optional rejection records preserve read order/counts and output values. */
    player_stock_view_component_rejection rejection = {0};
    context.rejection = &rejection;
    test.component = (component_fixture){0x202, 99, {0}, 0x1000};
    test.generation = 42; test.owner = 1; test.fail_read = 0;
    for (unsigned failed = 1; failed <= 4; ++failed) {
        rejection = (player_stock_view_component_rejection){0};
        test.calls = 0; test.fail_read = failed; result = 0x5a;
        assert(!player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result));
        assert(test.calls == failed && result == 0x5a);
        const char *reason = failed == 1 ? "component_read" : failed == 2 ? "parent_read" : "identity_readback";
        assert(rejection.reason && !strcmp(rejection.reason, reason));
    }
    test.fail_read = 0; test.calls = 0; rejection = (player_stock_view_component_rejection){0};
    assert(player_stock_view_component_route(&context, 1, (uintptr_t)&test.component, 0xa5, &result));
    assert(test.calls == 4 && result == 0 && !rejection.reason);
    uintptr_t pointer_result = 0xabcdef;
    test.calls = 0; rejection = (player_stock_view_component_rejection){0};
    assert(!player_stock_view_precompare_route(&context, (uintptr_t)&test.component, 0x1000, 0x9000, &pointer_result));
    assert(test.calls == 4 && pointer_result == 0xabcdef);
    assert(!strcmp(rejection.reason, "original_not_owned"));
    assert(rejection.component == (uintptr_t)&test.component && rejection.parent == 0x1000 &&
           rejection.class_pointer == 0x202 && rejection.runtime == 99 &&
           rejection.ancestor == 0x1000 && rejection.original == 0x9000);
    test.calls = 0; rejection = (player_stock_view_component_rejection){0};
    assert(!player_stock_view_precompare_route(&context, (uintptr_t)&test.component, 0x2000, 0x1000, &pointer_result));
    assert(test.calls == 4 && pointer_result == 0xabcdef && !strcmp(rejection.reason, "ancestor_mismatch"));
    return 0;
}
