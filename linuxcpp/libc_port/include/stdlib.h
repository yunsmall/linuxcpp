// 内核 libc 子集的 stdlib.h。
// 支持堆分配、整数转换、qsort/bsearch 和整数绝对值；进程/环境/locale
// 相关接口在内核里没有意义，调用点直接编译报错。

#pragma once

#include <__lcpp_port.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EXIT_SUCCESS 0
#define EXIT_FAILURE 1
#define RAND_MAX 2147483647

typedef struct {
	int quot;
	int rem;
} div_t;

typedef struct {
	long quot;
	long rem;
} ldiv_t;

typedef struct {
	long long quot;
	long long rem;
} lldiv_t;

/* 堆分配走 kmalloc(GFP_KERNEL)，只能在可睡眠上下文调用 */
void *malloc(size_t size);
void free(void *ptr);
void *calloc(size_t count, size_t size);
void *realloc(void *ptr, size_t size);

/* 整数转换；实际实现在 libc_port.c，出错时写 errno */
int atoi(const char *s);
long atol(const char *s);
long long atoll(const char *s);
long strtol(const char *s, char **end, int base);
long long strtoll(const char *s, char **end, int base);
unsigned long strtoul(const char *s, char **end, int base);
unsigned long long strtoull(const char *s, char **end, int base);

/* 排序/查找直接复用内核导出实现 */
void qsort(void *base, size_t nmemb, size_t size,
	   int (*compar)(const void *, const void *));
void *bsearch(const void *key, const void *base, size_t nmemb, size_t size,
	      int (*compar)(const void *, const void *));

static inline int abs(int value)
{
	return value < 0 ? -value : value;
}

static inline long labs(long value)
{
	return value < 0 ? -value : value;
}

static inline long long llabs(long long value)
{
	return value < 0 ? -value : value;
}

static inline div_t div(int numerator, int denominator)
{
	div_t result = { numerator / denominator, numerator % denominator };
	return result;
}

static inline ldiv_t ldiv(long numerator, long denominator)
{
	ldiv_t result = { numerator / denominator, numerator % denominator };
	return result;
}

static inline lldiv_t lldiv(long long numerator, long long denominator)
{
	lldiv_t result = { numerator / denominator, numerator % denominator };
	return result;
}

/* 浮点入口没有实现，内核不保存 FPU/SSE 状态 */
double atof(const char *s) LCPP_UNSUPPORTED("内核模块不能安全使用浮点");
double strtod(const char *s, char **end) LCPP_UNSUPPORTED("内核模块不能安全使用浮点");
float strtof(const char *s, char **end) LCPP_UNSUPPORTED("内核模块不能安全使用浮点");
long double strtold(const char *s, char **end) LCPP_UNSUPPORTED("内核模块不能安全使用浮点");

int rand(void) LCPP_UNSUPPORTED("内核里请用 get_random_u32");
void srand(unsigned int seed) LCPP_UNSUPPORTED("内核里请用 get_random_u32");

void abort(void) __attribute__((noreturn));
int atexit(void (*func)(void));

void exit(int status) LCPP_UNSUPPORTED("内核模块不能退出进程，请从 init 返回错误码");
void _Exit(int status) LCPP_UNSUPPORTED("内核模块不能退出进程，请从 init 返回错误码");
int at_quick_exit(void (*func)(void)) LCPP_UNSUPPORTED("内核模块没有进程退出流程");
void quick_exit(int status) LCPP_UNSUPPORTED("内核模块没有进程退出流程");
char *getenv(const char *name) LCPP_UNSUPPORTED("内核模块没有环境变量");
int system(const char *command) LCPP_UNSUPPORTED("内核模块不能执行用户态命令");
void *aligned_alloc(size_t alignment, size_t size)
	LCPP_UNSUPPORTED("请用内核 kmalloc 或 aligned operator new");

int mblen(const char *s, size_t n) LCPP_UNSUPPORTED("宽字符/多字节字符在内核里关闭");
int mbtowc(wchar_t *pwc, const char *s, size_t n) LCPP_UNSUPPORTED("宽字符在内核里关闭");
int wctomb(char *s, wchar_t wc) LCPP_UNSUPPORTED("宽字符在内核里关闭");
size_t mbstowcs(wchar_t *dst, const char *src, size_t n) LCPP_UNSUPPORTED("宽字符在内核里关闭");
size_t wcstombs(char *dst, const wchar_t *src, size_t n) LCPP_UNSUPPORTED("宽字符在内核里关闭");

#ifdef __cplusplus
}
#endif
