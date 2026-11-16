#include <stdint.h>
#include <stdbool.h>
#include <string.h>
typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;
static bool paused=true;
static double game=10;
void TestPause(bool v){paused=v;}
void TestGame(double v){game=v;}
bool IsGamePaused(void){return paused;}
bool IsPlayerValid(void){return true;}
const char *GetSaveFolderPath(void){return "/private/45841/save";}
double GetCurrentGameTime(void){return game;}
bool IsValidComponent(uint64_t id){return id==41 || id==43 || (id>=51 && id<=53);}
bool IsComponentOperational(uint64_t id){return id==41 || (id>=51 && id<=53);}
bool IsComponentClass(uint64_t id,const char *name){return (!strcmp(name,"ship") && id==41) || (!strcmp(name,"sector") && id==43) || (!strcmp(name,"station") && id>=51 && id<=53);}
uint64_t GetContextByClass(uint64_t id,const char *name,bool b){(void)b;return strcmp(name,"sector")==0 && (id==41 || (id>=51 && id<=53)) ? 43 : 0;}
const char *GetObjectIDCode(uint64_t id){switch(id){case 41:return "SHP-001";case 51:return "AAJ-808";case 52:return "UKN-243";case 53:return "RZT-476";default:return "";}}
UIPosRot GetObjectPositionInSector(uint64_t id){UIPosRot p={0,0,0,0,0,0};if(id==51)p.x=10;if(id==52)p.y=20;if(id==53)p.z=30;return p;}
