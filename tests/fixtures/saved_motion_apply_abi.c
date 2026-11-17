#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <math.h>
typedef uint64_t UniverseID;
typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;
static UIPosRot pose={0,0,0,1.57079632679f,0,0};
static UniverseID actor_zone=45;
static bool paused=false; static int reads=0;
static double game=10; static int writes=0; static float written_yaw; static bool recovery_code=false;
const char *GetSaveFolderPath(void){return "/private/45841/save";}
bool IsPlayerValid(void){return true;} bool IsGamePaused(void){return paused;}
bool IsValidComponent(UniverseID v){return v==41||v==43||v==45||v==99;}
bool IsComponentOperational(UniverseID v){return v==41;}
bool IsComponentClass(UniverseID v,const char*c){return (v==41&&!strcmp(c,"ship"))||(v==43&&!strcmp(c,"sector"))||(v==45&&!strcmp(c,"zone"))||(v==99&&!strcmp(c,"station"));}
UniverseID GetContextByClass(UniverseID v,const char*c,bool self){(void)self;if(v==41&&!strcmp(c,"sector"))return 43;if(v==41&&!strcmp(c,"zone"))return actor_zone;if(v==99&&!strcmp(c,"station"))return 99;return 0;}
UniverseID GetPlayerControlledShipID(void){return 0;} UniverseID GetPlayerOccupiedShipID(void){return 0;} UniverseID GetPlayerContainerID(void){return 99;}
const char* GetObjectIDCode(UniverseID v){return v==41?(recovery_code?"ENH-870":"WRG-830"):"";}
UIPosRot GetObjectPositionInSector(UniverseID v){(void)v;reads++;return pose;}
void SetObjectSectorPos(UniverseID a,UniverseID s,UIPosRot v){if(a!=41||s!=43)return;writes++;written_yaw=v.yaw;pose=v;pose.yaw*=0.017453292519943295f;pose.pitch*=0.017453292519943295f;pose.roll*=0.017453292519943295f;}
double GetCurrentGameTime(void){return game;}
void TestSetRecoveryCode(bool value){recovery_code=value;}
void TestAdvance(void){game=11;} int TestWrites(void){return writes;} float TestYaw(void){return written_yaw;}

void TestDrift(float x){pose.x=x;} void TestPause(bool value){paused=value;} int TestReads(void){return reads;}

void TestZone(UniverseID value){actor_zone=value;}
