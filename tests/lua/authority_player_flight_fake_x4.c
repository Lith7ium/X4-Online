/* Fake ABI for tests only, not linked into the game. */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#define SHIP UINT64_C(9007199254740993)
typedef struct {float x,y,z,yaw,pitch,roll;} UIPosRot;
static bool paused=true,rogue,invalid,zone_lost,occupied_lost,container_lost;static double game=3;static float pos;
void TestResume(void){paused=false;} void TestPause(void){paused=true;}
void TestGame(double t){game=t;} void TestRogue(void){rogue=true;}
void TestInvalid(void){invalid=true;} void TestPose(float x){pos=x;}
void TestZoneLost(void){zone_lost=true;} void TestOccupiedLost(void){occupied_lost=true;}
void TestContainerLost(void){container_lost=true;}
const char *GetSaveFolderPath(void){return "/tmp/45841/save";}
bool IsGamePaused(void){return paused;}
bool IsPlayerValid(void){return true;}
bool IsValidComponent(uint64_t n){return n==SHIP||n==11||n==12;}
bool IsComponentOperational(uint64_t n){return n==SHIP;}
bool IsComponentClass(uint64_t n,const char *c){return (!strcmp(c,"ship")&&n==SHIP)||(!strcmp(c,"sector")&&n==11)||(!strcmp(c,"zone")&&n==12);}
uint64_t GetContextByClass(uint64_t n,const char *c,bool self){(void)self;if(n!=SHIP)return 0;if(!strcmp(c,"sector"))return 11;if(!strcmp(c,"zone"))return zone_lost?0:12;return 0;}
uint64_t GetPlayerContainerID(void){return container_lost?0:SHIP;}
uint64_t GetPlayerOccupiedShipID(void){return occupied_lost?0:SHIP;}
uint64_t GetPlayerControlledShipID(void){return rogue?0:SHIP;}
double GetCurrentGameTime(void){return game;}
UIPosRot GetObjectPositionInSector(uint64_t n){(void)n;UIPosRot p={invalid?NAN:pos,2,3,0.1f,0.2f,0.3f};return p;}
