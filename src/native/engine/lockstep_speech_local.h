/* Spoken lines per client, DEFAULT ON in play (native_gate_speech_local = true; needs native_gate_speak_timer, whose stop
 * reason 139 and block pin it shares; Windows gate).
 *
 * X4 speaks for one player: scripts start a line because of where the player is (slot 1's ship on every client), and
 * U::EntitySpeakData::SpeakNextLine 0x561330 starts its voice sound on whatever PC runs it. So every client plays slot 1's
 * comm chatter, wherever its own player is, and a hot joiner plays the session's past chatter again while it replays the
 * ticks since its save (user report, 10 Nov: the first instance's combat chatter on the second). The simulation does not
 * need the sound: with the speak timer every line ends on its text timer.
 *
 * This client starts no voice sound (lockstep_speak_timer.h's second site, the je at 0x56163b as two nops) while
 *   - it is a hot joiner before its handover (the replay of the session's past), or
 *   - its own slot is not slot 1 and its ship is in another sector (class 0x58) than slot 1's player: the lines are about
 *     slot 1's surroundings.
 * A line that belongs to a player is that player's: while an MD frame of a cue slot k owns runs (lockstep_mission_owners.h:
 * a mission slot k accepted, the story of the start slot k took), the site holds the owner's answer - client k starts the
 * voice, every other client does not, a hot joiner's catch-up never - and the frame's end puts the step's answer back
 * (spl_owner_enter / spl_owner_leave, called by the frame rule on the simulation's thread). So slot 2's wingmate speaks on
 * client 2, wherever slot 1 is, and not on client 1. A line the speaker's own queue starts later, outside a frame, takes
 * the step's answer.
 * In slot 1's sector a client hears what slot 1 hears. Decided once per step in the probe's frame (gate.speech_local_frame:
 * the simulation's own thread, canonical state, so no line is being started while the site changes), by a 16-bit CAS. A
 * site that holds neither value is a failure of the speak timer's (its tick check stops, 139). An unseated slot (dead, in
 * a suit, walking) keeps the last answer. Not covered: lines X4 would speak for another player's own surroundings (never
 * started: the scripts ask about slot 1), other sounds of the replay (positional, at slot 1's camera until the handover). */
static int spl_armed,spl_muted;
static uint64_t spl_frames,spl_toggles,spl_catchup,spl_far,spl_near,spl_unknown;
static unsigned spl_owner_depth;   /* owned MD frames on the stack now */
static int spl_owner_before;       /* the step's answer the outermost of them found */
static uint64_t spl_owner_frames,spl_owner_played,spl_owner_muted;
static const char *spl_stage="idle";
static int join_catching_up(void);
static int (*spl_catching_up)(void)=join_catching_up;   /* tests replace it */
/* The class-0x58 (sector) ancestor of a component, itself included; NULL when none. */
static void *spl_sector_of(void *object) {
    unsigned char *p=object;
    for(unsigned depth=0;p && depth<24;depth++) {
        void **vtable=NULL;if(!read_local(p,&vtable,8) || !vtable) return NULL;
        int (*is_a)(void *,int)=NULL;if(!read_local((unsigned char*)vtable+0x11e8,&is_a,8) || !is_a) return NULL;
        if(is_a(p,0x58)) return p;
        if(!read_local(p+0x70,&p,8)) return NULL;
    }
    return NULL;
}
/* 1 mute, 0 play, -1 unknown (keep). */
static int spl_want(void) {
    if(spl_catching_up()) {++spl_catchup;return 1;}
    const unsigned slot=stats.slot;
    if(slot<2 || slot>PILOT_SLOTS) return 0;
    const pslot_slot *s=&pslots[slot];
    if(!s->seated || s->walking || !s->ship || !pslot_p1) {++spl_unknown;return -1;}
    void *mine=spl_sector_of(s->ship),*theirs=spl_sector_of(pslot_p1);
    if(!mine || !theirs) {++spl_unknown;return -1;}
    if(mine!=theirs) {++spl_far;return 1;}
    ++spl_near;return 0;
}
static int spl_set(int mute) {
    if(mute==spl_muted) return 1;
    if(!speak_site_swap(SPEAK_MUTE_SITE,mute?SPEAK_MUTE_ORIGINAL:SPEAK_MUTE_PATCHED,mute?SPEAK_MUTE_PATCHED:SPEAK_MUTE_ORIGINAL)) {
        spl_stage="cas";speak_timer_stage="mute_site";InterlockedIncrement64(&speak_timer_failures);return 0;
    }
    spl_muted=mute;++spl_toggles;return 1;
}
/* An MD frame of a cue slot k owns starts (the frame rule, on the simulation's thread): the lines it starts are slot k's. */
static void spl_owner_enter(unsigned k) {
    if(!spl_armed || !stats.active || k<2 || k>PILOT_SLOTS) return;
    if(spl_owner_depth++) return;   /* a frame inside a frame of the same scope: the outermost decides */
    spl_owner_before=spl_muted;++spl_owner_frames;
    const int mute=spl_catching_up() || stats.slot!=k;
    if(mute) ++spl_owner_muted;else ++spl_owner_played;
    (void)spl_set(mute);
}
/* ...and ends: the step's answer is back. */
static void spl_owner_leave(void) {
    if(!spl_owner_depth || --spl_owner_depth) return;
    if(spl_armed) (void)spl_set(spl_owner_before);
}
/* A player's own computer voice: the target readout. X4 reads the name of a newly selected target aloud (the game option
 * speaktargetname; U::Player's 0x705b80 queues the line on the speaker 0x703ac0 finds among the player's children, call
 * 0x561a10 at 0x705e7c). A slot's selection is replayed on every client, so every client read it aloud (a playtest
 * report of 14 Nov). The line itself stays on every client (its queue and timers are simulation state); only the voice
 * sound is the selecting player's:
 *   - the routine's own check of the option (call 0x1265960 at 0x705bc0) is where the speaker is noted: when the
 *     option is on, the speaker of the player the routine runs for (0x703ac0 on the singleton: the scope's player, slot
 *     1 outside every scope) is noted by its runtime ID with that slot. (The queueing call at 0x705e7c lies across two
 *     16-byte blocks, which the patcher does not write; build60 had it there and installed nothing.)
 *   - U::EntitySpeakData::SpeakNextLine 0x561330 starts the sound, later, from its own queue: its four call sites run
 *     it for a noted speaker (speak data +8 is the entity's ID) with the mute site holding that owner's answer (this
 *     client plays its own slot's, a hot joiner's catch-up nothing), and put the step's answer back after it.
 * Every other speaker and every other line of the session: as before. Sites and functions pinned; without them, or
 * without the slots' near page (a session of one), nothing is installed. Status lines=installed/noted/played/muted. */
#define SPL_OPTION 0x1265960u             /* (config, key, default) -> the option's value */
#define SPL_OPTION_HEAD 0x40u
#define SPL_OPTION_SHA "0f7ff3176475ae81a7d6a3cfe14ab108e22af757c411b56fb112d1de4667bb13"
#define SPL_OPTION_SITE 0x705bc0u         /* U::Player 0x705b80: is speaktargetname on */
#define SPL_SPEAKER 0x703ac0u             /* (player, &entity): the player's speaker among its children */
#define SPL_SPEAKER_SIZE 0x163u
#define SPL_SPEAKER_SHA "94108c4b1e32f39110a72c79323252d10ffe0ea9efe9d6de7c240d15d6648868"
#define SPL_NEXT 0x561330u                /* U::EntitySpeakData::SpeakNextLine(this) */
#define SPL_NEXT_HEAD 0x40u
#define SPL_NEXT_SHA "248067cc4ba6d799712da8f0a67780d1fd4444e59be09d46362050cb3c79f61e"
#define SPL_OPTION_STUB 0x180u            /* on the slots' near page, after the fade's (0x120, 0x140) */
#define SPL_NEXT_STUB 0x1a0u
#define SPL_SPEAKERS 8u
static const unsigned spl_next_sites[4]={0x562575u,0x5628cbu,0x564108u,0x9f07b4u};
typedef unsigned char (*spl_option_fn)(void *,const char *,unsigned char);
typedef void *(*spl_speaker_fn)(void *,void **);
typedef void (*spl_next_fn)(void *);
static spl_option_fn spl_option_original;static spl_speaker_fn spl_speaker_original;static spl_next_fn spl_next_original;   /* tests set their own */
static void *(*spl_player)(void);        /* tests: the player the routine runs for */
static struct {uint64_t id;unsigned owner;} spl_speakers[SPL_SPEAKERS];
static unsigned spl_speaker_next;
static int spl_lines_installed,spl_lines_tried;
static unsigned char spl_option_patched[5],spl_next_patched[4][5];
static volatile LONG64 spl_lines_noted,spl_lines_played,spl_lines_muted;
static void spl_speaker_note(uint64_t id,unsigned owner) {
    unsigned at=SPL_SPEAKERS;
    if(!id || !owner) return;
    for(unsigned i=0;i<SPL_SPEAKERS;i++) if(spl_speakers[i].id==id) {at=i;break;}
    if(at==SPL_SPEAKERS) {at=spl_speaker_next;spl_speaker_next=(spl_speaker_next+1u)%SPL_SPEAKERS;}
    spl_speakers[at].id=id;spl_speakers[at].owner=owner;
    InterlockedIncrement64(&spl_lines_noted);
}
/* The owner of a speak data's entity, noted before; 0 for every other one. */
static unsigned spl_speaker_owner(void *data) {
    uint64_t id=0;
    if(!data || !read_local((unsigned char*)data+8,&id,8) || !id) return 0;
    for(unsigned i=0;i<SPL_SPEAKERS;i++) if(spl_speakers[i].id==id) return spl_speakers[i].owner;
    return 0;
}
static unsigned char spl_option(void *config,const char *key,unsigned char fallback) {
    const unsigned char on=(spl_option_original?spl_option_original:(spl_option_fn)(image+SPL_OPTION))(config,key,fallback);
    if(on && spl_armed && stats.active && GetCurrentThreadId()==ui_thread) {
        void *player=spl_player?spl_player():(void*)pnat_player(),*entity=NULL;uint64_t id=0;
        __try {if(player) (void)(spl_speaker_original?spl_speaker_original:(spl_speaker_fn)(image+SPL_SPEAKER))(player,&entity);}
        __except(GetExceptionCode()==EXCEPTION_ACCESS_VIOLATION?EXCEPTION_EXECUTE_HANDLER:EXCEPTION_CONTINUE_SEARCH) {entity=NULL;}
        if(entity && read_local((unsigned char*)entity+8,&id,8)) spl_speaker_note(id,pstk_scope_slot?pstk_scope_slot:1u);
    }
    return on;
}
static void spl_next(void *data) {
    const spl_next_fn next=spl_next_original?spl_next_original:(spl_next_fn)(image+SPL_NEXT);
    const unsigned owner=spl_armed && stats.active && GetCurrentThreadId()==ui_thread?spl_speaker_owner(data):0;
    if(!owner) {next(data);return;}
    const int before=spl_muted,mute=spl_catching_up() || stats.slot!=owner;
    InterlockedIncrement64(mute?&spl_lines_muted:&spl_lines_played);
    (void)spl_set(mute);
    next(data);
    if(spl_armed) (void)spl_set(before);
}
static void spl_lines_install(void) {
    if(spl_lines_installed || spl_lines_tried || !pslot_page) return;
    spl_lines_tried=1;
    if(!hash_ok(image+SPL_OPTION,SPL_OPTION_HEAD,SPL_OPTION_SHA) || !hash_ok(image+SPL_SPEAKER,SPL_SPEAKER_SIZE,SPL_SPEAKER_SHA) ||
       !hash_ok(image+SPL_NEXT,SPL_NEXT_HEAD,SPL_NEXT_SHA)) return;
    unsigned done=0;
    for(;done<4;done++) {
        if(!pres_site_install(spl_next_sites[done],SPL_NEXT,SPL_NEXT_STUB,(void*)spl_next,spl_next_patched[done])) break;
        /* the speak timer's block check reads this site as the original call (lockstep_speak_timer.h) */
        const int32_t rel=(int32_t)(SPL_NEXT-(spl_next_sites[done]+5u));
        speak_timer_sites[done].rva=spl_next_sites[done];speak_timer_sites[done].original[0]=0xe8;memcpy(speak_timer_sites[done].original+1,&rel,4);
        memcpy(speak_timer_sites[done].patched,spl_next_patched[done],5);speak_timer_sites[done].on=1;
    }
    if(done==4 && pres_site_install(SPL_OPTION_SITE,SPL_OPTION,SPL_OPTION_STUB,(void*)spl_option,spl_option_patched)) {spl_lines_installed=1;return;}
    while(done) {--done;if(pres_site_uninstall(spl_next_sites[done],SPL_NEXT,spl_next_patched[done])) speak_timer_sites[done].on=0;}
}
static void spl_lines_restore(void) {
    if(!spl_lines_installed) return;
    int ok=pres_site_uninstall(SPL_OPTION_SITE,SPL_OPTION,spl_option_patched);
    for(unsigned i=0;i<4;i++) {
        if(pres_site_uninstall(spl_next_sites[i],SPL_NEXT,spl_next_patched[i])) speak_timer_sites[i].on=0;
        else ok=0;
    }
    if(ok) spl_lines_installed=0;
    memset(spl_speakers,0,sizeof(spl_speakers));
}
/* gate.speech_local(): before the first tick, after the speak timer (an identical rerun after a UI reload answers 1). */
static int spl_arm(void) {
    if(spl_armed) return stats.active!=0;
    if(!stats.active || GetCurrentThreadId()!=ui_thread || !speak_timer_installed || !speak_timer_patched) {spl_stage="refused";return 0;}
    if(speak_mute_site()!=SPEAK_MUTE_ORIGINAL) {spl_stage="site";return 0;}
    spl_frames=spl_toggles=spl_catchup=spl_far=spl_near=spl_unknown=0;spl_muted=0;spl_armed=1;spl_stage="armed";
    spl_owner_depth=0;spl_owner_before=0;spl_owner_frames=spl_owner_played=spl_owner_muted=0;
    spl_lines_tried=0;spl_speaker_next=0;memset(spl_speakers,0,sizeof(spl_speakers));return 1;
}
/* gate.speech_local_frame(): once per step, in the probe's frame. Answers the state (1 muted). */
static int spl_frame(void) {
    if(!spl_armed || !stats.active) return 0;
    ++spl_frames;
    spl_lines_install();   /* once, when the slots' near page is there */
    const int want=spl_want();
    if(want>=0) {
        if(spl_owner_depth) spl_owner_before=want;   /* never inside an owned frame in the probe's frame; kept right if it were */
        else (void)spl_set(want);
    }
    return spl_muted;
}
/* Stop: the site back before the speak timer's own restore. A foreign value stays. */
static void spl_restore(void) {
    spl_lines_restore();
    if(!spl_armed) return;
    if(spl_muted && speak_site_swap(SPEAK_MUTE_SITE,SPEAK_MUTE_PATCHED,SPEAK_MUTE_ORIGINAL)) spl_muted=0;
    spl_armed=0;spl_owner_depth=0;spl_stage="restored";
}
static int spl_status(char *out,size_t capacity) {
    int n=snprintf(out,capacity,"armed=%d muted=%d site=%04x frames=%llu toggles=%llu catchup=%llu far=%llu near=%llu unknown=%llu stage=%s "
        "owned=%llu/%llu/%llu lines=%d/%lld/%lld/%lld",
        spl_armed,spl_muted,speak_mute_site(),(unsigned long long)spl_frames,(unsigned long long)spl_toggles,(unsigned long long)spl_catchup,
        (unsigned long long)spl_far,(unsigned long long)spl_near,(unsigned long long)spl_unknown,spl_stage,
        (unsigned long long)spl_owner_frames,(unsigned long long)spl_owner_played,(unsigned long long)spl_owner_muted,
        spl_lines_installed,(long long)spl_lines_noted,(long long)spl_lines_played,(long long)spl_lines_muted);
    return n>0 && (size_t)n<capacity?n:0;
}
