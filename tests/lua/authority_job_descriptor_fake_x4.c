/* Synthetic, read-only X4 FFI surface for a process-local 64-bit actor. */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef struct {float x,y,z,yaw,pitch,roll;} UIPosRot;
static bool valid_context=true;
static int pose_reads=0;
int test_pose_reads(void) {return pose_reads;}
void test_context(bool v) {valid_context=v;}
const char *GetSaveFolderPath(void) {return "/tmp/45841/save";}
bool IsGamePaused(void) {return false;}
bool IsPlayerValid(void) {return true;}
bool IsValidComponent(uint64_t n) {return n==9007199254740993ULL || n==2;}
bool IsComponentOperational(uint64_t n) {return n==9007199254740993ULL;}
bool IsComponentClass(uint64_t n,const char *c) {
 return (!strcmp(c,"ship") && n==9007199254740993ULL) || (!strcmp(c,"sector") && n==2);
}
uint64_t GetContextByClass(uint64_t n,const char *c,bool self) {
 (void)self;return valid_context && n==9007199254740993ULL && !strcmp(c,"sector") ? 2:0;
}
UIPosRot GetObjectPositionInSector(uint64_t n) {(void)n;pose_reads++;UIPosRot p={1,2,3,0,0,0};return p;}
double GetCurrentGameTime(void) {return 10;}
