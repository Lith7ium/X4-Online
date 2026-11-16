/* Test-only X4 ABI, never loaded into the game. */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#define SHIP UINT64_C(9007199254740993)
const char *GetSaveFolderPath(void) { return "/tmp/45841/save"; }
bool IsGamePaused(void) { return true; }
bool IsPlayerValid(void) { return true; }
bool IsValidComponent(uint64_t n) {return n==SHIP || n==11 || n==12 || n==99;}
bool IsComponentOperational(uint64_t n) {return n==SHIP;}
bool IsComponentClass(uint64_t n,const char *c) {
 return (!strcmp(c,"ship") && n==SHIP) || (!strcmp(c,"sector") && n==11) || (!strcmp(c,"zone") && n==12);
}
uint64_t GetContextByClass(uint64_t n,const char *c,bool self) {
 (void)self;if(n!=SHIP)return 0;if(!strcmp(c,"sector"))return 11;if(!strcmp(c,"zone"))return 12;return 0;
}
double GetCurrentGameTime(void) {return 3;}
