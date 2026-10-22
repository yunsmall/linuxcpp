"""libc_port 自己实现的符号。

构建时拿这份列表和内核 Module.symvers 对比：如果某天内核也导出了同名
符号，至少能在构建日志里看到提醒，而不是等链接/加载时才发现。
"""

IMPLEMENTED = {
    "__errno_location",
    "atexit",
    "atoi",
    "atol",
    "atoll",
    "calloc",
    "free",
    "malloc",
    "perror",
    "printf",
    "putchar",
    "puts",
    "qsort",
    "realloc",
    "strdup",
    "strerror",
    "strndup",
    "strtol",
    "strtoll",
    "strtoul",
    "strtoull",
    "time",
    "timespec_get",
    "vprintf",
}
