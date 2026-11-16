#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <math.h>
typedef uint64_t UniverseID;
typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;
static UIPosRot pose={0,0,0,1.57079632679f,0,0};
static double game=10; static int writes=0; static float written_yaw;
const char *GetSaveFolderPath(void){return "/private/45841/save";}
bool IsPlayerValid(void){return true;} bool IsGamePaused(void){return false;}
bool IsValidComponent(UniverseID v){return v==41||v==43||v==45||v==99;}
bool IsComponentOperational(UniverseID v){return v==41;}
bool IsComponentClass(UniverseID v,const char*c){return (v==41&&!strcmp(c,"ship"))||(v==43&&!strcmp(c,"sector"))||(v==45&&!strcmp(c,"zone"))||(v==99&&!strcmp(c,"station"));}
UniverseID GetContextByClass(UniverseID v,const char*c,bool self){(void)self;if(v==41&&!strcmp(c,"sector"))return 43;if(v==41&&!strcmp(c,"zone"))return 45;if(v==99&&!strcmp(c,"station"))return 99;return 0;}
UniverseID GetPlayerControlledShipID(void){return 0;} UniverseID GetPlayerOccupiedShipID(void){return 0;} UniverseID GetPlayerContainerID(void){return 99;}
const char* GetObjectIDCode(UniverseID v){return v==41?"WRG-830":"";}
UIPosRot GetObjectPositionInSector(UniverseID v){(void)v;return pose;}
void SetObjectSectorPos(UniverseID a,UniverseID s,UIPosRot v){if(a!=41||s!=43)return;writes++;written_yaw=v.yaw;pose=v;}
double GetCurrentGameTime(void){return game;}
void TestAdvance(void){game=11;} int TestWrites(void){return writes;} float TestYaw(void){return written_yaw;}
