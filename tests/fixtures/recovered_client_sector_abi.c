/* Synthetic X4 ABI for the recovered client's sector reader. */
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
bool IsPlayerValid(void) { return true; }
bool IsGamePaused(void) { return false; }
const char *GetSaveFolderPath(void) { return "/private/45841/save"; }
uint64_t GetPlayerContainerID(void) { return 41; }
bool IsValidComponent(uint64_t value) { return value == 41 || value == 43; }
bool IsComponentClass(uint64_t value, const char *name) {
    return value == 43 && strcmp(name, "sector") == 0;
}
uint64_t GetContextByClass(uint64_t value, const char *name, bool self) {
    (void)self;
    return value == 41 && strcmp(name, "sector") == 0 ? 43 : 0;
}
