#include <stdint.h>
#include <stdbool.h>
#include <string.h>
static int mode=0;
void TestMode(int m){mode=m;}
bool IsPlayerValid(void){return mode!=1;}
const char *GetSaveFolderPath(void){return mode==2?"/unsafe/45841/save":"/private/45841/save";}
uint64_t GetPlayerContainerID(void){return mode==3?0:41;}
bool IsValidComponent(uint64_t v){return v==41||v==9007199254740993ULL;}
bool IsComponentClass(uint64_t v,const char *s){return v==9007199254740993ULL&&!strcmp(s,"sector");}
uint64_t GetContextByClass(uint64_t v,const char *s,bool self){(void)self;return v==41&&!strcmp(s,"sector")&&mode!=4?9007199254740993ULL:0;}
