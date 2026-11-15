/* Mock X4 symbols for LuaJIT pause fencing only, not engine behavior. */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
static bool paused=true;
static int writes=0;
typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;
void test_set_paused(bool value) { paused=value; }
int test_writes(void) { return writes; }
const char *GetSaveFolderPath(void) { return "/tmp/45841/save"; }
bool IsGamePaused(void) { return paused; }
bool IsValidComponent(uint64_t v) { return v!=0; }
bool IsComponentOperational(uint64_t v) { return v==1; }
bool IsComponentClass(uint64_t v,const char *name) { return v==1 && !strcmp(name,"ship"); }
uint64_t GetContextByClass(uint64_t v,const char *name,bool self) {
 (void)self;
 if (v==1 && !strcmp(name,"sector")) return 2;
 if (v==1 && !strcmp(name,"zone")) return 3;
 if (v==4 && !strcmp(name,"station")) return 5;
 return 0;
}
uint64_t GetPlayerControlledShipID(void) { return 0; }
uint64_t GetPlayerOccupiedShipID(void) { return 0; }
uint64_t GetPlayerContainerID(void) { return 4; }
UIPosRot GetObjectPositionInSector(uint64_t v) { (void)v; UIPosRot p={0,0,0,0,0,0};return p; }
void SetObjectSectorPos(uint64_t v,uint64_t s,UIPosRot p) { (void)v;(void)s;(void)p;writes++; }
