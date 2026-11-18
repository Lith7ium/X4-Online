#include <stdint.h>
#include <stdbool.h>
#include <string.h>
typedef uint64_t UniverseID;
static bool paused=false,live=true;static UniverseID zone=45;static char save_path[512]="/private/45841/save";
void TestPause(bool v){paused=v;} void TestLive(bool v){live=v;} void TestZone(uint64_t v){zone=v;}
void TestSetSavePath(const char *v){if(v && strlen(v)<sizeof(save_path))strcpy(save_path,v);}
bool IsPlayerValid(void){return true;} bool IsGamePaused(void){return paused;}
const char *GetSaveFolderPath(void){return save_path;}
bool IsValidComponent(UniverseID v){return v==41 ? live : (v==43 || v==45 || v==46);}
bool IsComponentOperational(UniverseID v){return v==41 && live;}
bool IsComponentClass(UniverseID v,const char *c){return (v==41 && !strcmp(c,"ship")) || (v==43 && !strcmp(c,"sector")) || ((v==45 || v==46) && !strcmp(c,"zone"));}
UniverseID GetContextByClass(UniverseID v,const char *c,bool self){(void)self;if(v!=41)return 0;if(!strcmp(c,"sector"))return 43;if(!strcmp(c,"zone"))return zone;return 0;}
