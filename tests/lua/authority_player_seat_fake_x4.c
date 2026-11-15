/* Synthetic, read-only API surface. Never linked into X4. */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef struct {float x,y,z,yaw,pitch,roll;} UIPosRot;
const char *GetSaveFolderPath(void) {return "/tmp/45841/save";}
bool IsGamePaused(void) {return true;}
bool IsPlayerValid(void) {return true;}
bool IsValidComponent(uint64_t n) {return n==10 || n==11 || n==12 || n==13 || n==14 || n==99;}
bool IsComponentOperational(uint64_t n) {return n==10 || n==12 || n==14;}
bool IsComponentClass(uint64_t n,const char *c) {
 return (!strcmp(c,"ship") && (n==10 || n==12 || n==14)) || (!strcmp(c,"sector") && (n==11 || n==13));
}
uint64_t GetContextByClass(uint64_t n,const char *c,bool self) {
 (void)self;if(strcmp(c,"sector"))return 0;if(n==10 || n==14)return 11;if(n==12)return 13;return 0;
}
UIPosRot GetObjectPositionInSector(uint64_t n) {UIPosRot p={(float)n,1,2,0,0,0};return p;}
