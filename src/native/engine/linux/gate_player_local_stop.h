#ifndef X4_GATE_PLAYER_LOCAL_STOP_H
#define X4_GATE_PLAYER_LOCAL_STOP_H
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

/* Launcher capability, deliberately independent of relay ownership. Optional
 * X4_DEV_PLAYER_STOP_FD names an inherited anonymous pipe's read-only,
 * nonblocking end. Only gate_tick entry may establish the OS-thread owner.
 * Shared wait polls reject foreign/concurrent/reentrant opt-in callers before
 * accessing fd fields. No signal handler runs native cleanup. Original fd is
 * never read/closed. Private duplicate stays resident
 * until process exit. There is no restoration/resume path, even before takeover.
 * Byte 'S' requests stop; EOF/malformed input/fault also terminate fail-closed.
 * Window-close handling and preemption of blocked native calls are not provided. */
enum { PLAYER_LOCAL_STOP_INVALID = 226, PLAYER_LOCAL_STOP_REQUEST = 227,
       PLAYER_LOCAL_STOP_EOF = 228, PLAYER_LOCAL_STOP_FAULT = 229,
       PLAYER_LOCAL_STOP_THREAD = 230 };
enum { PLAYER_LOCAL_STOP_UNCONFIGURED, PLAYER_LOCAL_STOP_ABSENT,
       PLAYER_LOCAL_STOP_INITIALIZING, PLAYER_LOCAL_STOP_READY, PLAYER_LOCAL_STOP_POLLING };
static _Atomic unsigned player_local_stop_state;
static _Atomic long player_local_stop_owner;
/* Plain capability fields are accessed only by the owner after acquire of
 * READY and exclusive transition to POLLING. INITIALIZING publishes none. */
static int player_local_stop_fd = -1;
static dev_t player_local_stop_device;
static ino_t player_local_stop_inode;

static _Noreturn void player_local_stop_terminal(unsigned reason) {
    unsigned ownership = atomic_load_explicit(&player_dispatch_stop_ownership, memory_order_acquire);
    if (ownership == PLAYER_DISPATCH_REQUESTED || ownership == PLAYER_DISPATCH_PUBLISHED)
        finish(reason); /* Existing takeover latch exits before any cleanup. */
    /* A launcher stop before takeover must not turn into ordinary singleplayer. */
    player_dispatch_stop_terminate(reason, ownership, "local-launcher");
}
static int player_local_stop_pipe(int fd, struct stat *status) {
    int flags = fcntl(fd, F_GETFL);
    if (flags < 0 || (flags & O_ACCMODE) != O_RDONLY || !(flags & O_NONBLOCK) ||
        fstat(fd, status) || !S_ISFIFO(status->st_mode)) return 0;
    char name[64], target[64];
    int length = snprintf(name, sizeof name, "/proc/self/fd/%d", fd);
    if (length <= 0 || (size_t)length >= sizeof name) return 0;
    ssize_t size = readlink(name, target, sizeof target);
    if (size <= 7 || (size_t)size >= sizeof target || memcmp(target, "pipe:[", 6) || target[size-1] != ']') return 0;
    for (ssize_t i = 6; i < size-1; ++i) if (target[i] < '0' || target[i] > '9') return 0;
    return 1;
}
static unsigned player_local_stop_configure(unsigned main_boundary) {
    unsigned state = atomic_load_explicit(&player_local_stop_state, memory_order_acquire);
    if (state != PLAYER_LOCAL_STOP_UNCONFIGURED) return state;
    const char *text = getenv("X4_DEV_PLAYER_STOP_FD");
    if (text && !main_boundary) player_local_stop_terminal(PLAYER_LOCAL_STOP_THREAD);
    unsigned next = text ? PLAYER_LOCAL_STOP_INITIALIZING : PLAYER_LOCAL_STOP_ABSENT;
    if (!atomic_compare_exchange_strong_explicit(&player_local_stop_state, &state, next,
                                                 memory_order_acq_rel, memory_order_acquire)) return state;
    if (!text) return PLAYER_LOCAL_STOP_ABSENT;
    atomic_store_explicit(&player_local_stop_owner, (long)syscall(SYS_gettid), memory_order_relaxed);
    const char *dispatch = getenv("X4_DEV_WORKER_DISPATCH");
    if (!dispatch || strcmp(dispatch, "1") || !*text || (*text == '0' && text[1]))
        player_local_stop_terminal(PLAYER_LOCAL_STOP_INVALID);
    unsigned descriptor = 0;
    for (const char *p = text; *p; ++p) {
        if (*p < '0' || *p > '9' || descriptor > ((unsigned)INT_MAX - (unsigned)(*p-'0')) / 10)
            player_local_stop_terminal(PLAYER_LOCAL_STOP_INVALID);
        descriptor = descriptor * 10 + (unsigned)(*p-'0');
    }
    if (descriptor < 3) player_local_stop_terminal(PLAYER_LOCAL_STOP_INVALID);
    struct stat original, owned;
    if (!player_local_stop_pipe((int)descriptor, &original))
        player_local_stop_terminal(PLAYER_LOCAL_STOP_INVALID);
    int duplicate = fcntl((int)descriptor, F_DUPFD_CLOEXEC, 3);
    if (duplicate < 0 || !player_local_stop_pipe(duplicate, &owned) ||
        owned.st_dev != original.st_dev || owned.st_ino != original.st_ino)
        player_local_stop_terminal(PLAYER_LOCAL_STOP_INVALID);
    player_local_stop_device = owned.st_dev;
    player_local_stop_inode = owned.st_ino;
    player_local_stop_fd = duplicate;
    atomic_store_explicit(&player_local_stop_state, PLAYER_LOCAL_STOP_READY, memory_order_release);
    return PLAYER_LOCAL_STOP_READY;
}
static void player_local_stop_poll_at(unsigned main_boundary) {
    int incoming_errno = errno;
    unsigned state = player_local_stop_configure(main_boundary);
    if (state == PLAYER_LOCAL_STOP_ABSENT) { errno = incoming_errno; return; }
    if (state != PLAYER_LOCAL_STOP_READY ||
        atomic_load_explicit(&player_local_stop_owner, memory_order_relaxed) != (long)syscall(SYS_gettid))
        player_local_stop_terminal(PLAYER_LOCAL_STOP_THREAD);
    /* Also reject same-thread reentry while libc/read is in progress. Never
     * wait for another caller or allow two reads of this capability. */
    if (!atomic_compare_exchange_strong_explicit(&player_local_stop_state, &state, PLAYER_LOCAL_STOP_POLLING,
                                                 memory_order_acq_rel, memory_order_acquire))
        player_local_stop_terminal(PLAYER_LOCAL_STOP_THREAD);
    struct stat owned;
    if (!player_local_stop_pipe(player_local_stop_fd, &owned) ||
        owned.st_dev != player_local_stop_device || owned.st_ino != player_local_stop_inode ||
        fcntl(player_local_stop_fd, F_GETFD) != FD_CLOEXEC)
        player_local_stop_terminal(PLAYER_LOCAL_STOP_FAULT);
    char bytes[2];
    ssize_t count = read(player_local_stop_fd, bytes, sizeof bytes);
    if (count < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            atomic_store_explicit(&player_local_stop_state, PLAYER_LOCAL_STOP_READY, memory_order_release);
            errno = incoming_errno; return;
        }
        player_local_stop_terminal(PLAYER_LOCAL_STOP_FAULT);
    }
    if (!count) player_local_stop_terminal(PLAYER_LOCAL_STOP_EOF);
    if (count == 1 && bytes[0] == 'S') player_local_stop_terminal(PLAYER_LOCAL_STOP_REQUEST);
    player_local_stop_terminal(PLAYER_LOCAL_STOP_INVALID);
}
static void player_local_stop_poll(void) { player_local_stop_poll_at(0); }
/* Sole production callsite: gate_tick entry, before optional interlock/native
 * forwarding. This mirrors the gate's existing first-entry main identity. */
static void player_local_stop_main_poll(void) { player_local_stop_poll_at(1); }
#endif
