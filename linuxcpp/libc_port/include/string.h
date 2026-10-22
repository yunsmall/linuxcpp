// 内核 string.h：大部分函数由内核导出，少数在 libc_port.c 里补。
// locale 相关和带全局状态的接口在内核里不使用，调用点直接报错。

#pragma once

#include <__lcpp_port.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

void *memcpy(void *dst, const void *src, size_t n);
void *memmove(void *dst, const void *src, size_t n);
void *memset(void *dst, int c, size_t n);
int memcmp(const void *a, const void *b, size_t n);
void *memchr(const void *s, int c, size_t n);

char *strcpy(char *dst, const char *src);
char *strncpy(char *dst, const char *src, size_t n);
char *strcat(char *dst, const char *src);
char *strncat(char *dst, const char *src, size_t n);
int strcmp(const char *a, const char *b);
int strncmp(const char *a, const char *b, size_t n);
char *strchr(const char *s, int c);
char *strrchr(const char *s, int c);
size_t strcspn(const char *s, const char *reject);
char *strpbrk(const char *s, const char *accept);
char *strstr(const char *haystack, const char *needle);
size_t strspn(const char *s, const char *accept);
size_t strlen(const char *s);
size_t strnlen(const char *s, size_t maxlen);

/* 以下三个在 libc_port.c 里实现，分配走 GFP_KERNEL */
char *strerror(int errnum);
char *strdup(const char *s);
char *strndup(const char *s, size_t n);

int strcoll(const char *a, const char *b) LCPP_UNSUPPORTED("内核没有 locale");
size_t strxfrm(char *dst, const char *src, size_t n) LCPP_UNSUPPORTED("内核没有 locale");
char *strtok(char *s, const char *delim)
	LCPP_UNSUPPORTED("strtok 依赖全局状态，内核里请手写解析或加锁");

#ifdef __cplusplus
}
#endif
