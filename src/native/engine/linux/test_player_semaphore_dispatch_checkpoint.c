#define _GNU_SOURCE
#include <assert.h>
#include <pthread.h>
#include <sys/wait.h>
#include "player_semaphore_observer_preload.c"
#include "player_worker_dispatch_adapter.h"

static player_worker_dispatch_adapter adapter;
static frame_worker_recurring rendezvous = FRAME_WORKER_RECURRING_INIT;
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static unsigned permits;
static _Thread_local uint64_t thread_id = 1, ticket;
static unsigned lost_callback;
static _Atomic unsigned callback_count;
static unsigned sealed_callbacks, sealed_receipts;

static uint64_t clock_ms(void *context) {
    (void)context;
    struct timespec now;
    assert(!clock_gettime(CLOCK_MONOTONIC, &now));
    return (uint64_t)now.tv_sec * 1000 + (uint64_t)now.tv_nsec / 1000000;
}

static void pause_ms(void *context) {
    (void)context;
    struct timespec pause = {0, 1000000};
    nanosleep(&pause, NULL);
}

static int snapshot(void *context, unsigned *count, unsigned *maximum) {
    (void)context;
    assert(!pthread_mutex_lock(&mutex));
    *count = permits;
    *maximum = 1;
    assert(!pthread_mutex_unlock(&mutex));
    return 1;
}

static uint64_t native_post(void *semaphore, unsigned count) {
    assert(semaphore == TARGET_SEMAPHORE && count == 1);
    assert(!pthread_mutex_lock(&mutex));
    assert(!permits);
    permits = 1;
    assert(!pthread_mutex_unlock(&mutex));
    return 1;
}

static uint64_t native_wait(void *semaphore) {
    assert(semaphore == TARGET_SEMAPHORE);
    assert(!pthread_mutex_lock(&mutex));
    assert(permits == 1);
    permits = 0;
    assert(!pthread_mutex_unlock(&mutex));
    return 1;
}

static void callback(unsigned kind, unsigned returning, uintptr_t caller,
                     uint64_t argument, uint64_t result, unsigned movement) {
    (void)caller; (void)argument; (void)result;
    atomic_fetch_add(&callback_count, 1);
    if (lost_callback && kind == 2 && returning && ticket == 400) return;
    if (kind == 1) {
        assert(thread_id == 1);
        assert(returning ? pwda_post_return(&adapter, thread_id) : pwda_post_begin(&adapter, thread_id));
    } else {
        assert(kind == 2 && movement && thread_id == 2);
        assert(returning ? pwda_wait_return(&adapter, thread_id, ticket) :
                           pwda_pre_wait(&adapter, thread_id, &ticket));
    }
}

static void *worker(void *unused) {
    (void)unused;
    thread_id = 2;
    assert(x4mp_semaphore_observer_movement_scope(1));
    for (uint64_t generation = 399; generation <= 401; ++generation) {
        assert(x4mp_semaphore_observer_wait(TARGET_SEMAPHORE) == 1);
        /* A callback lost after closure must not grant the next join. */
        if (lost_callback && generation == 400) {
            assert(!pwda_join(&adapter, thread_id, ticket));
            assert(pwda_phase(&adapter) == PWDA_FAILED);
            _exit(42);
        }
        assert(ticket == generation && pwda_join(&adapter, thread_id, ticket));
        assert(fwrr_worker_arrive(&rendezvous, generation, thread_id) == FWRR_OK);
        fwrr_token token = {0};
        fwrr_result admission;
        while ((admission = fwrr_worker_try_enter(&rendezvous, generation, thread_id, &token)) == FWRR_WAIT) {
            pause_ms(NULL);
        }
        assert(admission == FWRR_WORKER_ENTERED);
        if (generation == 399) {
            assert(x4mp_semaphore_observer_checkpoint(generation) == 1);
            sealed_callbacks = atomic_load(&callback_count);
            sealed_receipts = atomic_load(&receipt_count);
            assert(atomic_load(&observation_state) == OBSERVATION_CLOSED);
        } else {
            assert(atomic_load(&receipt_count) == sealed_receipts);
            assert(atomic_load(&callback_count) > sealed_callbacks);
        }
        assert(fwrr_worker_release(&rendezvous, generation, thread_id, &token) == FWRR_OK);
        assert(pwda_tail(&adapter, thread_id, &ticket));
    }
    assert(x4mp_semaphore_observer_movement_scope(0));
    return NULL;
}

static void run(unsigned corrupt) {
    lost_callback = corrupt;
    receipt_fd = open("/dev/null", O_WRONLY);
    assert(receipt_fd >= 0);
    atomic_store(&constructor_state, 2);
    originals[1] = (void *)native_post;
    originals[2] = (void *)native_wait;
    adapter.snapshot = snapshot;
    adapter.clock_ms = clock_ms;
    adapter.pause = pause_ms;
    adapter.timeout_ms = 1000;
    assert(pwda_request(&adapter, 1, 2, 399, &rendezvous));
    assert(pwda_post_begin(&adapter, 1) && pwda_post_return(&adapter, 1));
    assert(x4mp_semaphore_dispatch_register(callback));
    assert(!x4mp_semaphore_dispatch_register(callback));
    pthread_t worker_thread;
    assert(!pthread_create(&worker_thread, NULL, worker, NULL));
    assert(fwrr_initialize_at(&rendezvous, 1, 2, 399));
    for (uint64_t generation = 399; generation <= 401; ++generation) {
        assert(pwda_arm(&adapter, generation, 1));
        assert(fwrr_arm(&rendezvous, generation, 1) == FWRR_OK);
        assert(pwda_publish_arm(&adapter));
        assert(x4mp_semaphore_observer_post(TARGET_SEMAPHORE, 1) == 1);
        assert(fwrr_main_park(&rendezvous, generation, 1) == FWRR_OK);
        fwrr_result completion;
        while ((completion = fwrr_main_poll(&rendezvous, generation, 1)) == FWRR_WAIT) {
            pause_ms(NULL);
        }
        assert(completion == FWRR_MAIN_RETURN_ALLOWED);
    }
    assert(!pthread_join(worker_thread, NULL));
    assert(!ticket && pwda_phase(&adapter) == PWDA_TAIL);
    assert(!x4mp_semaphore_observer_incomplete());
    assert(x4mp_semaphore_observer_checkpoint(401) == 0); /* No second interval. */
    close(receipt_fd);
}

int main(void) {
    for (unsigned corrupt = 0; corrupt <= 1; ++corrupt) {
        pid_t child = fork();
        assert(child >= 0);
        if (!child) { run(corrupt); _exit(0); }
        int status;
        assert(waitpid(child, &status, 0) == child);
        assert(WIFEXITED(status) && WEXITSTATUS(status) == (corrupt ? 42 : 0));
    }
    puts("actual checkpoint API: resident dispatch continues; lost callback and duplicate closure reject");
}
