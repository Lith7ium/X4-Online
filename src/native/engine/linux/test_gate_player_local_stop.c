/* Real gate permit wait and forwarding, scripted send/recv: no socket/game. */
#define main unused_gate_fixture_main
#include "test_gate_linux.c"
#undef main
enum { LOCAL_DEFAULT, LOCAL_EMPTY, LOCAL_REQUEST, LOCAL_EOF, LOCAL_MALFORMED,
       LOCAL_CLOSED, LOCAL_REUSED, LOCAL_ORIGINAL_REUSED, LOCAL_BLOCKING,
       LOCAL_PRETAKEOVER, LOCAL_BAD_CONFIG, LOCAL_REGULAR, LOCAL_WRONG_ACCESS,
       LOCAL_BAD_FLAGS, LOCAL_ENV_PINNED, LOCAL_NETWORK_FAULT, LOCAL_BAD_NUMBER,
       LOCAL_CONCURRENT_DEFAULT, LOCAL_FOREIGN_EARLY, LOCAL_FOREIGN_READY,
       LOCAL_CONCURRENT_INIT, LOCAL_CONCURRENT_READ, LOCAL_REENTRY };
static unsigned local_case, receive_calls;
static _Atomic unsigned thread_stage;
static pthread_barrier_t default_barrier;
static int control_pipe[2], unrelated_pipe[2];
static struct { unsigned forwarded, terminal; } *local_markers;
static void local_forward(void *frame, unsigned char loading) {
    (void)frame; (void)loading; ++local_markers->forwarded;
}
/* Pause the genuine initializer/read in libc, then call actual gate/wait
 * entry points from a second OS thread. It must terminate without inspecting
 * partially initialized capability fields or entering a competing read. */
ssize_t __real_readlink(const char *path, char *buffer, size_t size);
ssize_t __wrap_readlink(const char *path, char *buffer, size_t size) {
    if (local_case == LOCAL_CONCURRENT_INIT &&
        atomic_load(&player_local_stop_state) == PLAYER_LOCAL_STOP_INITIALIZING) {
        atomic_store(&thread_stage, 1);
        for (;;) sched_yield(); /* foreign entry terminates this whole child */
    }
    return __real_readlink(path, buffer, size);
}
ssize_t __real_read(int fd, void *buffer, size_t size);
ssize_t __wrap_read(int fd, void *buffer, size_t size) {
    if (atomic_load(&player_local_stop_state) == PLAYER_LOCAL_STOP_POLLING && fd == player_local_stop_fd) {
        if (local_case == LOCAL_REENTRY) { player_local_stop_poll(); _exit(94); }
        if (local_case == LOCAL_CONCURRENT_READ) {
            atomic_store(&thread_stage, 1);
            for (;;) sched_yield();
        }
    }
    return __real_read(fd, buffer, size);
}
static void *foreign_poll(void *unused) {
    (void)unused;
    if (local_case == LOCAL_CONCURRENT_DEFAULT) {
        int status = pthread_barrier_wait(&default_barrier);
        assert(!status || status == PTHREAD_BARRIER_SERIAL_THREAD);
        for (unsigned i = 0; i < 100; ++i) assert(!closed_window());
        return NULL;
    }
    if (local_case == LOCAL_CONCURRENT_INIT || local_case == LOCAL_CONCURRENT_READ)
        while (!atomic_load(&thread_stage)) sched_yield();
    if (local_case == LOCAL_CONCURRENT_INIT) gate_tick((void *)0x1234, 0);
    else (void)closed_window();
    _exit(93); /* An opt-in foreign call must never return or forward. */
}
ssize_t __real_write(int fd, const void *buffer, size_t length);
ssize_t __wrap_write(int fd, const void *buffer, size_t length) {
    const char prefix[] = "X4LAN WORKER_DISPATCH_TERMINAL ";
    if (length >= sizeof prefix - 1 && !memcmp(buffer, prefix, sizeof prefix - 1)) {
        ++local_markers->terminal;
        assert(!keyboard_probe_closed && !local_markers->forwarded);
        /* Neither inherited original nor unrelated/reused descriptors are
         * closed by native stop, including the private-fd reuse failure. */
        assert(fcntl(unrelated_pipe[0], F_GETFD) >= 0);
        if (local_case == LOCAL_REUSED) assert(fcntl(player_local_stop_fd, F_GETFD) >= 0);
        if (local_case == LOCAL_ORIGINAL_REUSED) assert(fcntl(control_pipe[0], F_GETFD) >= 0);
    }
    return __real_write(fd, buffer, length);
}
ssize_t __wrap_send(int fd, const void *buffer, size_t length, int flags) {
    (void)buffer; (void)flags; assert(fd == 777); return (ssize_t)length;
}
ssize_t __wrap_recv(int fd, void *buffer, size_t length, int flags) {
    (void)flags; assert(fd == 777); ++receive_calls;
    assert(atomic_load(&player_local_stop_state) != PLAYER_LOCAL_STOP_UNCONFIGURED);
    if (receive_calls == 1) {
        if (local_case == LOCAL_REQUEST || local_case == LOCAL_ORIGINAL_REUSED)
            assert(write(control_pipe[1], "S", 1) == 1);
        if (local_case == LOCAL_EOF) assert(!close(control_pipe[1]));
        if (local_case == LOCAL_MALFORMED) assert(write(control_pipe[1], "bad", 3) == 3);
        if (local_case == LOCAL_CLOSED || local_case == LOCAL_REUSED) {
            assert(!close(player_local_stop_fd));
            if (local_case == LOCAL_REUSED)
                assert(dup2(unrelated_pipe[0], player_local_stop_fd) == player_local_stop_fd);
        }
        if (local_case == LOCAL_BLOCKING)
            assert(!fcntl(player_local_stop_fd, F_SETFL, O_RDONLY));
        /* Exercise a receive timeout before the valid permit. The intervening
         * no-stop poll must preserve recv's errno instead of masking faults. */
        errno = local_case == LOCAL_NETWORK_FAULT ? EBADF : EWOULDBLOCK; return -1;
    }
    char reply[160];
    int count = snprintf(reply, sizeof reply, "NGGO|3|%s|1|1||", secret);
    assert(count > 0 && (size_t)count <= length); memcpy(buffer, reply, (size_t)count);
    return count;
}
static void local_child(unsigned which, int start_fd) {
    char go; assert(read(start_fd, &go, 1) == 1); close(start_fd);
    reset_session(); local_case = which; receive_calls = 0;
    unsetenv("X4_DEV_PLAYER_STOP_FD"); unsetenv("X4_DEV_WORKER_DISPATCH");
    gate_frame_tick = local_forward;
    keyboard_probe_requested = 1; keyboard_probe_closed = 0;
    atomic_store(&player_recurring_mode, 1); /* This fixture owns no worker hooks. */
    if (which != LOCAL_DEFAULT && which != LOCAL_CONCURRENT_DEFAULT) {
        char descriptor[32]; snprintf(descriptor, sizeof descriptor, "%d", control_pipe[0]);
        setenv("X4_DEV_PLAYER_STOP_FD", descriptor, 1);
        setenv("X4_DEV_WORKER_DISPATCH", "1", 1);
    }
    if (which == LOCAL_BAD_NUMBER) setenv("X4_DEV_PLAYER_STOP_FD", "01", 1);
    if (which == LOCAL_BAD_CONFIG) unsetenv("X4_DEV_WORKER_DISPATCH");
    if (which == LOCAL_REGULAR) {
        int fd = open("/dev/null", O_RDONLY | O_NONBLOCK); assert(fd >= 3);
        char descriptor[32]; snprintf(descriptor, sizeof descriptor, "%d", fd);
        setenv("X4_DEV_PLAYER_STOP_FD", descriptor, 1);
    }
    if (which == LOCAL_WRONG_ACCESS) {
        char descriptor[32]; snprintf(descriptor, sizeof descriptor, "%d", control_pipe[1]);
        setenv("X4_DEV_PLAYER_STOP_FD", descriptor, 1);
    }
    if (which == LOCAL_BAD_FLAGS) assert(!fcntl(control_pipe[0], F_SETFL, O_RDONLY));
    pthread_t foreign;
    if (which == LOCAL_CONCURRENT_DEFAULT) {
        assert(!pthread_barrier_init(&default_barrier, NULL, 2));
        assert(!pthread_create(&foreign, NULL, foreign_poll, NULL));
        int status = pthread_barrier_wait(&default_barrier);
        assert(!status || status == PTHREAD_BARRIER_SERIAL_THREAD);
        for (unsigned i = 0; i < 100; ++i) player_local_stop_main_poll();
        assert(!pthread_join(foreign, NULL));
        assert(atomic_load(&player_local_stop_state) == PLAYER_LOCAL_STOP_ABSENT);
        assert(!atomic_load(&player_local_stop_owner) && player_local_stop_fd == -1);
    }
    if (which == LOCAL_FOREIGN_EARLY) {
        assert(!pthread_create(&foreign, NULL, foreign_poll, NULL));
        assert(!pthread_join(foreign, NULL)); _exit(92);
    }
    if (which == LOCAL_CONCURRENT_INIT || which == LOCAL_CONCURRENT_READ)
        assert(!pthread_create(&foreign, NULL, foreign_poll, NULL));
    if (which == LOCAL_PRETAKEOVER) {
        assert(write(control_pipe[1], "S", 1) == 1);
        stats.active = 0;
        gate_tick((void *)0x1234, 0); /* Must never reach ordinary native call. */
        _exit(98);
    }
    if (which != LOCAL_DEFAULT && which != LOCAL_CONCURRENT_DEFAULT) {
        errno = EDOM; player_local_stop_main_poll(); assert(errno == EDOM);
        assert(player_local_stop_fd != control_pipe[0]);
        assert(fcntl(player_local_stop_fd, F_GETFD) == FD_CLOEXEC);
    }
    if (which == LOCAL_FOREIGN_READY) {
        assert(player_dispatch_stop_claim()); player_dispatch_stop_published();
        assert(!pthread_create(&foreign, NULL, foreign_poll, NULL));
        assert(!pthread_join(foreign, NULL)); _exit(91);
    }
    if (which == LOCAL_ENV_PINNED) {
        setenv("X4_DEV_PLAYER_STOP_FD", "invalid-new-environment", 1);
        unsetenv("X4_DEV_WORKER_DISPATCH");
    }
    if (which == LOCAL_ORIGINAL_REUSED) {
        assert(!close(control_pipe[0]));
        assert(dup2(unrelated_pipe[0], control_pipe[0]) == control_pipe[0]);
    }
    assert(player_dispatch_stop_claim()); player_dispatch_stop_published();
    stats.active = 1; stats.slot = 1; stats.game = getd(LX_GAME_VA);
    timeout_ms = 1000; connection = 777; wire_version = 3; blob_proposal[0] = 0;
    strcpy(secret, "0123456789abcdef0123456789abcdef");
    char reply[256];
    unsigned reason = gate_wait_permit("test", 4, reply, sizeof reply);
    if (which == LOCAL_NETWORK_FAULT) { assert(reason == 8); finish(reason); _exit(97); }
    assert(!reason);
    gate_original_once((void *)0x1234, 0);
    assert(local_markers->forwarded == 1 && receive_calls == 2 && !local_markers->terminal);
    assert(fcntl(control_pipe[0], F_GETFD) >= 0 && fcntl(unrelated_pipe[0], F_GETFD) >= 0);
    _exit(0);
}
int main(void) {
    synth_image();
    local_markers = mmap(NULL, sizeof *local_markers, PROT_READ | PROT_WRITE,
                        MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    assert(local_markers != MAP_FAILED);
    /* An unrelated process must survive every terminal route. It is forked
     * before control pipes exist, so it cannot keep their writers alive. */
    int sibling_pipe[2]; assert(!pipe(sibling_pipe));
    pid_t sibling = fork(); assert(sibling >= 0);
    if (!sibling) { alarm(15); close(sibling_pipe[1]); char byte; assert(read(sibling_pipe[0], &byte, 1) == 1); _exit(0); }
    close(sibling_pipe[0]);
    for (unsigned which = LOCAL_DEFAULT; which <= LOCAL_REENTRY; ++which) {
        *local_markers = (__typeof__(*local_markers)){0};
        assert(!pipe2(control_pipe, O_NONBLOCK | O_CLOEXEC));
        assert(!pipe2(unrelated_pipe, O_NONBLOCK | O_CLOEXEC));
        assert(write(unrelated_pipe[1], "U", 1) == 1);
        int start[2]; assert(!pipe(start));
        pid_t child = fork(); assert(child >= 0);
        if (!child) { close(start[1]); local_child(which, start[0]); }
        close(start[0]); close(control_pipe[1]);
        assert(write(start[1], "G", 1) == 1); close(start[1]);
        int status; assert(waitpid(child, &status, 0) == child && WIFEXITED(status));
        unsigned normal = which == LOCAL_DEFAULT || which == LOCAL_EMPTY || which == LOCAL_ENV_PINNED || which == LOCAL_CONCURRENT_DEFAULT;
        assert(WEXITSTATUS(status) == (normal ? 0 : 225));
        assert(local_markers->forwarded == normal && local_markers->terminal == !normal);
        char untouched; assert(read(unrelated_pipe[0], &untouched, 1) == 1 && untouched == 'U');
        assert(!kill(sibling, 0));
        close(control_pipe[0]); close(unrelated_pipe[0]); close(unrelated_pipe[1]);
    }
    assert(write(sibling_pipe[1], "Q", 1) == 1); close(sibling_pipe[1]);
    int status; assert(waitpid(sibling, &status, 0) == sibling && WIFEXITED(status) && !WEXITSTATUS(status));
    puts("local launcher stop: real permit wait, default/empty, STOP/EOF/faults, fd reuse and sibling isolation and concurrent ownership ok");
}
