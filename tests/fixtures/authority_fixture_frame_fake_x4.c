#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;
static bool paused = true;
static double game = 10;
static int slot = 1;
void TestPause(bool value) { paused = value; }
void TestGame(double value) { game = value; }
void TestSlot(int value) { slot = value; }
bool IsGamePaused(void) { return paused; }
bool IsPlayerValid(void) { return true; }
const char *GetSaveFolderPath(void) { return "/private/45841/save"; }
double GetCurrentGameTime(void) { return game; }
bool IsValidComponent(uint64_t id) { return id == 41 || id == 43 || (id >= 51 && id <= 53); }
bool IsComponentOperational(uint64_t id) { return id == 41 || (id >= 51 && id <= 53); }
bool IsComponentClass(uint64_t id, const char *name) {
    return (!strcmp(name, "ship") && id == 41) || (!strcmp(name, "sector") && id == 43) ||
           (!strcmp(name, "station") && id >= 51 && id <= 53);
}
uint64_t GetContextByClass(uint64_t id, const char *name, bool self) {
    (void)self;
    return !strcmp(name, "sector") && (id == 41 || (id >= 51 && id <= 53)) ? 43 : 0;
}
const char *GetObjectIDCode(uint64_t id) {
    static const char *first[] = {"SLS-778", "MRY-123", "MYO-569"};
    static const char *second[] = {"FPJ-079", "OSK-110", "JFP-464"};
    if (id == 41) return "SHP-001";
    return id >= 51 && id <= 53 ? (slot == 1 ? first[id-51] : second[id-51]) : "";
}
UIPosRot GetObjectPositionInSector(uint64_t id) {
    UIPosRot pose = {0,0,0,0,0,0};
    if (id == 52) pose.x = 2000;
    if (id == 53) pose.y = 2000;
    return pose;
}
