// 内核 freestanding 环境的最小 time.h，只提供类型和声明。

#pragma once

#include <__lcpp_port.h>
#include <bits/types.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

struct timespec {
	time_t tv_sec;
	long tv_nsec;
};

struct tm {
	int tm_sec;
	int tm_min;
	int tm_hour;
	int tm_mday;
	int tm_mon;
	int tm_year;
	int tm_wday;
	int tm_yday;
	int tm_isdst;
	long tm_gmtoff;
	const char *tm_zone;
};

#define CLOCKS_PER_SEC 1000000L
#define TIME_UTC 1

clock_t clock(void) LCPP_UNSUPPORTED("内核没有 POSIX clock()，请用 ktime_get");
double difftime(time_t end, time_t beginning)
	LCPP_UNSUPPORTED("内核模块不能安全使用浮点返回值");
time_t mktime(struct tm *tm) LCPP_UNSUPPORTED("内核没有时区/locale，不能做 mktime");
time_t time(time_t *result);
char *asctime(const struct tm *tm) LCPP_UNSUPPORTED("内核没有 locale");
char *ctime(const time_t *timer) LCPP_UNSUPPORTED("内核没有 locale");
struct tm *gmtime(const time_t *timer) LCPP_UNSUPPORTED("内核没有时区/locale");
struct tm *localtime(const time_t *timer) LCPP_UNSUPPORTED("内核没有时区/locale");
size_t strftime(char *s, size_t maxsize, const char *format, const struct tm *tm)
	LCPP_UNSUPPORTED("内核没有 locale/时区，不能做 strftime");
int timespec_get(struct timespec *ts, int base);

#ifdef __cplusplus
}
#endif
