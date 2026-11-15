#include <assert.h>
#include <stdio.h>
#include "stock_keyboard_replay.h"
static unsigned applied, wanted[2], prepared;
static int prepare(void *context, uint64_t tick, const uint64_t saved[2], const stock_input_record records[2]) {
    (void)context; assert(tick == 5 && saved[0] == 111 && saved[1] == 222 && !applied);
    wanted[0] = !!(records[0].flags & STOCK_INPUT_FIRE);
    wanted[1] = !!(records[1].flags & STOCK_INPUT_FIRE);
    prepared = 1; return 1;
}
static int apply(void *context, uint64_t tick, unsigned slot, uint64_t saved, const stock_input_record *record) {
    (void)context; assert(prepared && tick == 5 && saved == (slot == 1 ? 111u : 222u));
    assert(!!(record->flags & STOCK_INPUT_FIRE) == wanted[slot - 1]); ++applied; return 1;
}
static void setup(keyboard_replay *replay, unsigned primary) {
    keyboard_replay_config config = {.own_slot=1, .delay=2, .first_capture=3, .last_capture=5,
        .saved_ship_ids={111,222}, .independent_players=1, .cursor_active_only=1, .primary_fire=primary};
    assert(keyboard_replay_init(replay));
    assert(keyboard_replay_configure(replay, &config) == KEYBOARD_REPLAY_OK);
    assert(keyboard_replay_begin(replay, 3) == KEYBOARD_REPLAY_OK);
    assert(keyboard_replay_publish_slots_prepared(replay,3,NULL,apply,NULL)==KEYBOARD_REPLAY_NOT_DUE);
}
static unsigned seal(keyboard_replay *replay, unsigned held, unsigned char *out) {
    const float cursor[3] = {0}; unsigned length=0;
    assert(keyboard_replay_seal_primary_presentation(replay, cursor, NULL, held, out, STOCK_INPUT_MAX_BYTES, &length) == KEYBOARD_REPLAY_OK);
    return length;
}
static void pair(unsigned one, unsigned two, unsigned tamper) {
    keyboard_replay replay; setup(&replay, 1); applied=prepared=0;
    unsigned char local[STOCK_INPUT_MAX_BYTES], remote[STOCK_INPUT_MAX_BYTES], unused[STOCK_INPUT_MAX_BYTES];
    const float cursor[3]={0};unsigned rejected_length=0;
    assert(keyboard_replay_seal_presentation(&replay,cursor,NULL,local,sizeof local,&rejected_length)==KEYBOARD_REPLAY_ARGUMENT);
    unsigned size=seal(&replay,one,local); memcpy(remote,local,size);
    remote[1]=(unsigned char)((remote[1]&~STOCK_INPUT_FIRE)|(two?STOCK_INPUT_FIRE:0));
    if (tamper==1) local[1]^=STOCK_INPUT_FIRE; /* own echo must remain byte-exact */
    if (tamper==2) remote[1]|=STOCK_INPUT_SECONDARY_FIRE;
    keyboard_replay_result first=keyboard_replay_stage(&replay,1,local,size);
    keyboard_replay_result second=keyboard_replay_stage(&replay,2,remote,size);
    if (tamper) {
        assert(first<0 || second<0); assert(!applied && !prepared);
    } else {
        assert(first==KEYBOARD_REPLAY_OK && second==KEYBOARD_REPLAY_OK);
        assert(keyboard_replay_begin(&replay,4)==KEYBOARD_REPLAY_OK);
        assert(keyboard_replay_publish_slots_prepared(&replay,4,NULL,apply,NULL)==KEYBOARD_REPLAY_NOT_DUE);seal(&replay,0,unused);
        assert(keyboard_replay_begin(&replay,5)==KEYBOARD_REPLAY_OK);
        assert(keyboard_replay_publish_slots_prepared(&replay,5,prepare,apply,NULL)==KEYBOARD_REPLAY_OK);
        seal(&replay,1,unused);
        assert(!(unused[1]&STOCK_INPUT_FIRE)); /* final held source becomes delayed drain */
        assert(applied==2 && wanted[0]==one && wanted[1]==two);
        assert(keyboard_replay_publish_slots_prepared(&replay,5,prepare,apply,NULL)==KEYBOARD_REPLAY_DUPLICATE);
        assert(applied==2);
        stock_input_record bad={0};bad.flags=STOCK_INPUT_FIRE|STOCK_INPUT_ACTIVE;bad.capture16=5;
        assert(!keyboard_replay_record_valid(&replay,&bad,2));
        bad.capture16=4;bad.flags=STOCK_INPUT_FIRE;
        assert(!keyboard_replay_record_valid(&replay,&bad,2));
    }
    keyboard_replay_stop(&replay);assert(keyboard_replay_destroy(&replay));
}
int main(void) {
    for(unsigned one=0;one<2;++one)for(unsigned two=0;two<2;++two)pair(one,two,0);
    pair(1,0,1);pair(1,0,2);
    keyboard_replay replay;setup(&replay,0);
    float cursor[3]={0};unsigned char out[STOCK_INPUT_MAX_BYTES];unsigned length=0;
    assert(keyboard_replay_seal_primary_presentation(&replay,cursor,NULL,1,out,sizeof out,&length)==KEYBOARD_REPLAY_ARGUMENT);
    seal(&replay,0,out);out[1]|=STOCK_INPUT_FIRE;
    assert(keyboard_replay_stage(&replay,2,out,43)<0);
    keyboard_replay_stop(&replay);assert(keyboard_replay_destroy(&replay));
    puts("primary stock replay: independent wants, tamper, secondary, delayed drain and default rejection PASS");
}
