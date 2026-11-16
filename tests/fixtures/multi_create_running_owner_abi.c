#include <stdbool.h>
static bool paused=true;
static double game=100;
void TestReset(void){paused=true;game=100;}
void TestUnpause(void){paused=false;}
void TestPause(void){paused=true;}
void TestAdvance(double v){game+=v;}
bool IsPlayerValid(void){return true;}
bool IsGamePaused(void){return paused;}
double GetCurrentGameTime(void){return game;}
const char *GetSaveFolderPath(void){return "/private/45841/save";}
#include <stdint.h>
#include <string.h>
typedef uint64_t UniverseID;
typedef struct {float x,y,z,yaw,pitch,roll;} UIPosRot;
bool IsValidComponent(UniverseID v){return v==41 || v==43;}
bool IsComponentOperational(UniverseID v){return v==41;}
bool IsComponentClass(UniverseID v,const char *c){return (v==41 && !strcmp(c,"ship")) || (v==43 && !strcmp(c,"sector"));}
UniverseID GetContextByClass(UniverseID v,const char *c,bool r){(void)r;return v==41 && !strcmp(c,"sector") ? 43 : 0;}
UIPosRot GetObjectPositionInSector(UniverseID v){(void)v;UIPosRot p={-400,100000,500,0,0,0};return p;}
