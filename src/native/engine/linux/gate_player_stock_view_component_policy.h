#ifndef X4_GATE_PLAYER_STOCK_VIEW_COMPONENT_POLICY_H
#define X4_GATE_PLAYER_STOCK_VIEW_COMPONENT_POLICY_H

/* Include after gate_player_stock_view_fov.h. The coordinator must bind only
 * after the initial transaction commits: ship identities are then immutable,
 * and the provider's release/acquire binding publishes them to foreign threads.
 * This header does not bind or activate a hook. */
#include "player_stock_view_component_policy.h"
#include "player_stock_view_control_proof.h"
#include <errno.h>
#include <unistd.h>

/* The context points only to the caller's stack-local rejection record. */
static int stock_view_component_gate_refuse(void *context, const char *reason) {
    player_stock_view_component_rejection *rejection = context;
    if (rejection && !rejection->reason) rejection->reason = reason;
    return 0;
}

static int stock_view_component_gate_read(void *context, uintptr_t address, void *out, unsigned size) {
    (void)context;
    return read_local((void *)address, out, size);
}

static int stock_view_component_registry_read(void *context, uintptr_t address, void *out, size_t size) {
    (void)context;
    return read_local((void *)address, out, size);
}

/* Pinned Linux 9.00 U::ShipExtraSmall primary vtable, offset-to-top 0.
 * RTTI 0x3c84968 names N1U14ShipExtraSmallE at 0x2d49ef0 and derives
 * directly from U::Ship (typeinfo 0x3c727b0). This exact class is eligible
 * only for authenticated foreign pass-through; it never becomes an owned slot. */
#define STOCK_VIEW_COMPONENT_FOREIGN_XS_VTABLE 0x3d282a8u

static int stock_view_component_gate_foreign(void *context, uintptr_t component,
                                             uint64_t component_runtime, uintptr_t parent) {
    struct { uintptr_t class_pointer; uint64_t runtime; } ship, after;
    if (!parent || parent > UINTPTR_MAX - sizeof ship)
        return stock_view_component_gate_refuse(context, "foreign_parent_arguments");
    if (!read_local((void *)parent, &ship, sizeof ship))
        return stock_view_component_gate_refuse(context, "foreign_parent_read");
    if (context) {
        player_stock_view_component_rejection *rejection = context;
        rejection->parent_class = ship.class_pointer;
        rejection->parent_runtime = ship.runtime;
    }
    if ((ship.class_pointer != (uintptr_t)LX(SEAT_PREFLIGHT_SHIP_VTABLE) &&
         ship.class_pointer != (uintptr_t)LX(STOCK_VIEW_COMPONENT_FOREIGN_XS_VTABLE)) || !ship.runtime)
        return stock_view_component_gate_refuse(context, "foreign_parent_identity");
    const player_stock_view_control_ops registry = {
        .read = stock_view_component_registry_read,
        .registry_global = (uintptr_t)LX(0x3daa860),
    };
    if (!stock_view_control_registry(&registry, component, component_runtime))
        return stock_view_component_gate_refuse(context, "foreign_component_registry");
    if (!stock_view_control_registry(&registry, parent, ship.runtime))
        return stock_view_component_gate_refuse(context, "foreign_parent_registry");
    if (!read_local((void *)parent, &after, sizeof after))
        return stock_view_component_gate_refuse(context, "foreign_parent_readback");
    if (ship.class_pointer != after.class_pointer || ship.runtime != after.runtime)
        return stock_view_component_gate_refuse(context, "foreign_parent_changed");
    return 1;
}

static int stock_view_component_gate_authenticate(void *context, unsigned expected_slot, uint64_t *generation) {
    unsigned actual_slot = 0;
    if (!generation || expected_slot < 1 || expected_slot > 2)
        return stock_view_component_gate_refuse(context, "owner_arguments");
    if (!stock_view_gate_owner(stock_view_gate_controllers[expected_slot - 1], &actual_slot))
        return stock_view_component_gate_refuse(context, "owner_authentication");
    if (factory_probe_identity.ship != stock_view_gate_ships[0])
        return stock_view_component_gate_refuse(context, "factory_ship_identity");
    if (lifecycle_discard_ship != stock_view_gate_ships[1])
        return stock_view_component_gate_refuse(context, "lifecycle_ship_identity");
    if (actual_slot != expected_slot)
        return stock_view_component_gate_refuse(context, "owner_slot");
    *generation = stats.issued;
    return 1;
}

static player_stock_view_component_context stock_view_component_gate_context(player_stock_view_component_rejection *rejection) {
    const player_stock_view_component_context context = {
        .context = rejection,
        .rejection = rejection,
        .read = stock_view_component_gate_read,
        .authenticate = stock_view_component_gate_authenticate,
        .foreign_identity = stock_view_component_gate_foreign,
        .ships = {stock_view_gate_ships[0], stock_view_gate_ships[1]},
        .classes = {(uintptr_t)LX(0x3c6a440), (uintptr_t)LX(0x3ccad80)},
        .state = &stock_view_gate_state,
    };
    return context;
}

/* Failure receipts consume only the saved context/rejection, never engine reads.
 * Formatting and retries stay bounded even when stderr is unavailable. */
static size_t stock_view_component_receipt_literal(char *out, size_t used, const char *literal) {
    while (*literal && used < 511u) out[used++] = *literal++;
    return used;
}
static size_t stock_view_component_receipt_hex(char *out, size_t used, uint64_t value) {
    static const char digits[] = "0123456789abcdef";
    for (unsigned shift = 64; shift && used < 511u; shift -= 4)
        out[used++] = digits[(value >> (shift - 4)) & 15u];
    return used;
}
static void stock_view_component_gate_receipt(const char *policy,
        const player_stock_view_component_context *context,
        const player_stock_view_component_rejection *rejection) {
    int saved_errno = errno;
    char receipt[512];
    size_t used = stock_view_component_receipt_literal(receipt, 0, "X4 VIEW COMPONENT_REJECT policy=");
    used = stock_view_component_receipt_literal(receipt, used, policy);
    used = stock_view_component_receipt_literal(receipt, used, " reason=");
    used = stock_view_component_receipt_literal(receipt, used, rejection->reason ? rejection->reason : "unspecified");
    const char *names[] = {" component=", " parent=", " class=", " runtime=", " ancestor=", " original=", " ship1=", " ship2=", " parent_class=", " parent_runtime="};
    const uint64_t values[] = {rejection->component, rejection->parent, rejection->class_pointer,
        rejection->runtime, rejection->ancestor, rejection->original, context->ships[0], context->ships[1],
        rejection->parent_class, rejection->parent_runtime};
    for (unsigned field = 0; field < sizeof values / sizeof values[0]; ++field) {
        used = stock_view_component_receipt_literal(receipt, used, names[field]);
        used = stock_view_component_receipt_hex(receipt, used, values[field]);
    }
    receipt[used++] = '\n';
    size_t sent = 0;
    for (unsigned attempt = 0; attempt < 4 && sent < used; ++attempt) {
        ssize_t written = write(STDERR_FILENO, receipt + sent, used - sent);
        if (written > 0) sent += (size_t)written;
        else if (written == 0 || errno != EINTR) break;
    }
    errno = saved_errno;
}

static int stock_view_component_gate_policy(unsigned site, uintptr_t component,
                                             unsigned char original, unsigned char *result) {
    player_stock_view_component_rejection rejection = {.component = component, .original = original};
    player_stock_view_component_context context = stock_view_component_gate_context(&rejection);
    int accepted = player_stock_view_component_route(&context, site, component, original, result);
    if (!accepted) stock_view_component_gate_receipt(site == 0 ? "floating" : "external", &context, &rejection);
    return accepted;
}

static int stock_view_precompare_gate_policy(uintptr_t component, uintptr_t ancestor,
                                              uintptr_t original, uintptr_t *result) {
    player_stock_view_component_rejection rejection = {.component = component, .ancestor = ancestor, .original = original};
    player_stock_view_component_context context = stock_view_component_gate_context(&rejection);
    int accepted = player_stock_view_precompare_route(&context, component, ancestor, original, result);
    if (!accepted) stock_view_component_gate_receipt("precompare", &context, &rejection);
    return accepted;
}
#endif
