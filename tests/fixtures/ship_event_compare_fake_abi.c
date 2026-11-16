#include <stdbool.h>
#include <stdint.h>
#include <string.h>
bool IsValidComponent(uint64_t id){return id==9007199254740993ULL || id==9007199254740994ULL;}
bool IsComponentClass(uint64_t id,const char *klass){return IsValidComponent(id) && !strcmp(klass,"ship");}
