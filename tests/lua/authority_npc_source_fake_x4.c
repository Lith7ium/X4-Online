/* Fake source-only X4 exports; deliberately no object setter. */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
static bool paused=true;static float x;static double gametime;
typedef struct {float x,y,z,yaw,pitch,roll;} UIPosRot;
void test_state(bool p,float pos,double time) {paused=p;x=pos;gametime=time;}
const char *GetSaveFolderPath(void) {return "/tmp/45841/save";}
bool IsGamePaused(void) {return paused;}
bool IsPlayerValid(void) {return true;}
bool IsValidComponent(uint64_t v) {return v!=0;}
bool IsComponentOperational(uint64_t v) {return v==1;}
bool IsComponentClass(uint64_t v,const char *s) {return v==1 && !strcmp(s,"ship");}
uint64_t GetContextByClass(uint64_t v,const char *s,bool self) {
 (void)self;if(v==1 && !strcmp(s,"sector"))return 2;if(v==1 && !strcmp(s,"zone"))return 3;
 if(v==4 && !strcmp(s,"station"))return 5;return 0;
}
uint64_t GetPlayerControlledShipID(void) {return 0;}
uint64_t GetPlayerOccupiedShipID(void) {return 0;}
uint64_t GetPlayerContainerID(void) {return 4;}
UIPosRot GetObjectPositionInSector(uint64_t v) {(void)v;UIPosRot p={x,0,0,0,0,0};return p;}
double GetCurrentGameTime(void) {return gametime;}
