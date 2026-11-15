#ifndef X4_PLAYER_VIEW_FAILURE_RECEIPT_H
#define X4_PLAYER_VIEW_FAILURE_RECEIPT_H
#include <errno.h>
#include <stddef.h>
#include <unistd.h>

/* Failure-only literal receipts: no allocation, formatting, locks or engine reads.
 * Bound retries even if stderr is interrupted or accepts only partial writes.
 * Receipt failure still ends with the same fail-closed process exit code. */
static inline __attribute__((noreturn)) void player_view_failure_exit(const char *text, size_t length) {
    int saved_errno = errno;
    for (unsigned attempt = 0; length && attempt < 4; ++attempt) {
        ssize_t count = write(STDERR_FILENO, text, length);
        if (count > 0) {
            text += count;
            length -= (size_t)count;
        } else if (count == 0 || errno != EINTR) {
            break;
        }
    }
    errno = saved_errno;
    _exit(223);
}
#define PLAYER_VIEW_FAILURE(reason) \
    player_view_failure_exit("X4 VIEW FATAL reason=" reason "\n", sizeof("X4 VIEW FATAL reason=" reason "\n") - 1)
#endif
