#include <stdbool.h>
#include <stdint.h>
#include <string.h>
static bool paused=true;
static double game=100;
void TestReset(void){paused=true;game=100;}
void TestPause(void){paused=true;}
void TestResume(void){paused=false;}
void TestAdvance(void){if(!paused)game+=1;}
bool IsGamePaused(void){return paused;}
bool IsPlayerValid(void){return true;}
double GetCurrentGameTime(void){return game;}
const char* GetSaveFolderPath(void){return "/private/45841/save";}
bool IsValidComponent(uint64_t id){return id==42;}
bool IsComponentClass(uint64_t id,const char *name){return id==42 && !strcmp(name,"ship");}
