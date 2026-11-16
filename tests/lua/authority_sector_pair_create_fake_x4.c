/* Test-only fake UI exports; no game code. */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef struct {float x,y,z,yaw,pitch,roll;} UIPosRot;
const char *GetSaveFolderPath(void){return "/tmp/45841/save";}
bool IsGamePaused(void){return true;}
bool IsPlayerValid(void){return true;}
bool IsValidComponent(uint64_t n){return n==10||n==11;}
bool IsComponentOperational(uint64_t n){return n==10;}
bool IsComponentClass(uint64_t n,const char *c){return (n==10&&!strcmp(c,"ship"))||(n==11&&!strcmp(c,"sector"));}
uint64_t GetContextByClass(uint64_t n,const char *c,bool self){(void)self;return n==10&&!strcmp(c,"sector")?11:0;}
UIPosRot GetObjectPositionInSector(uint64_t n){UIPosRot p={-399.125f,100000.0f,500.25f,0,0,0};(void)n;return p;}
double GetCurrentGameTime(void){return 42;}
