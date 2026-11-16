/* Fake ABI for readback logic; not used in X4. */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#define TARGET UINT64_C(9007199254740993)
static int state;
static bool npc_lost;
void TestDropNPC(void){npc_lost=true;}
void TestMove(void){state=1;}
void TestReset(void){state=0;}
void TestRogue(void){state=2;}
const char *GetSaveFolderPath(void){return "/tmp/45841/save";}
bool IsGamePaused(void){return true;}
bool IsPlayerValid(void){return true;}
bool IsValidComponent(uint64_t v){return v==TARGET || v==11 || v==10 || (v==13 && !npc_lost);}
bool IsComponentOperational(uint64_t v){return v==TARGET || v==10 || v==13;}
bool IsComponentClass(uint64_t v,const char *k){return (!strcmp(k,"ship")&&(v==TARGET||v==10||v==13))||(!strcmp(k,"sector")&&v==11);}
uint64_t GetContextByClass(uint64_t v,const char *k,bool self){(void)self;if(!strcmp(k,"ship")&&(v==10||v==TARGET||v==13))return v;if(!strcmp(k,"sector")&&(v==10||v==TARGET||v==13))return 11;return 0;}
uint64_t GetPlayerContainerID(void){return state==1?TARGET:state==2?13:10;}
uint64_t GetPlayerOccupiedShipID(void){return state==1?TARGET:state==2?13:10;}
uint64_t GetPlayerControlledShipID(void){return state==1?TARGET:state==2?13:10;}
double GetCurrentGameTime(void){return 3;}
