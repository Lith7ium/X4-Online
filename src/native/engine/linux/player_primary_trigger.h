#ifndef X4_PLAYER_PRIMARY_TRIGGER_H
#define X4_PLAYER_PRIMARY_TRIGGER_H

#include <stdint.h>
#include <string.h>

/* Replicate only fields written by the pinned stock no-target constructor.
 * Allocation padding remains untouched. Times are the native worker TLS time. */
static inline void primary_trigger_construct(unsigned char *controller, uintptr_t base_vtable,
                                             uintptr_t mindless_vtable, double first, double second) {
    uint64_t zero = 0;
    uint16_t zero16 = 0;
    float range = -1.0f;
    double unset = -1.0;
    memcpy(controller, &base_vtable, 8);
    for (unsigned offset = 8; offset <= 0x18; offset += 8) {
        memcpy(controller + offset, &zero, 8);
    }
    memcpy(controller + 0x20, &first, 8);
    memset(controller + 0x28, 0, 4);
    memcpy(controller + 0x30, &second, 8);
    memcpy(controller + 0x40, &zero, 8);
    memcpy(controller + 0x80, &range, 4);
    memcpy(controller + 0x84, &zero16, 2);
    controller[0x86] = 0;
    memcpy(controller, &mindless_vtable, 8);
    memcpy(controller + 0x90, &zero16, 2);
    for (unsigned offset = 0x38; offset <= 0x50; offset += 8) {
        if (offset != 0x40) memcpy(controller + offset, &unset, 8);
    }
    memcpy(controller + 0x88, &unset, 8);
    memset(controller + 0x60, 0, 0x20);
}

/* Developer script only: Linux input policy still rejects the shared FIRE bit. */
static inline unsigned primary_trigger_script(uint64_t generation, uint64_t apply) {
    return generation >= apply && generation - apply >= 30 && generation - apply < 36;
}
#endif
