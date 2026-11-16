#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef uint64_t UniverseID;
typedef struct {float x,y,z,yaw,pitch,roll;} UIPosRot;
static int mode;
static unsigned calls;
void TestMode(int value){mode=value;calls=0;}
bool IsPlayerValid(void){return mode!=1;}
bool IsGamePaused(void){return mode!=2;}
bool IsValidComponent(UniverseID v){return v==UINT64_MAX || v==42;}
bool IsComponentOperational(UniverseID v){return v==UINT64_MAX && mode!=3;}
bool IsComponentClass(UniverseID v,const char *c){return (v==UINT64_MAX && !strcmp(c,"ship")) || (v==42 && !strcmp(c,"sector"));}
UniverseID GetContextByClass(UniverseID v,const char *c,bool r){(void)r;return v==UINT64_MAX && !strcmp(c,"sector") && mode!=4 ? 42 : 0;}
UIPosRot GetObjectPositionInSector(UniverseID v){(void)v;UIPosRot p={1.25f,-2.5f,3.75f,0,0,0};if(mode==5)p.x=99;return p;}
double GetCurrentGameTime(void){return mode==6 ? ++calls : 100.0;}
const char* GetSaveFolderPath(void){return mode==7 ? "/unsafe/other/save" : "/private/45841/save";}
