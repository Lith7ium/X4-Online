#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned calls, mode;
static int result_fd;
static ssize_t interrupted_write(int fd, const void *text, size_t length) {
    (void)fd; (void)text; (void)length;
    ++calls;
    errno = mode == 2 ? EIO : EINTR;
    return mode == 1 ? 1 : -1;
}
static __attribute__((noreturn)) void checked_exit(int status) {
    int result[2] = {errno, (int)calls};
    assert(write(result_fd, result, sizeof result) == sizeof result);
    _exit(status);
}
#define write interrupted_write
#define _exit checked_exit
#include "player_view_failure_receipt.h"
#undef write
#undef _exit

int main(void) {
    for (mode = 0; mode < 3; ++mode) {
        int output[2]; assert(!pipe(output));
        pid_t child = fork(); assert(child >= 0);
        if (!child) {
            close(output[0]); result_fd = output[1]; errno = EDOM;
            PLAYER_VIEW_FAILURE("fixture");
        }
        close(output[1]);
        int result[2], status;
        assert(read(output[0], result, sizeof result) == sizeof result); close(output[0]);
        assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 223);
        assert(result[0] == EDOM && result[1] == (mode == 2 ? 1 : 4));
    }
}
