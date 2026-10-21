/* 由 gen_libc_shim.py 生成，不要手改 */
#pragma once
#ifdef __cplusplus
extern "C" {
#endif
void *memcpy(void *, const void *, __SIZE_TYPE__);
void *memmove(void *, const void *, __SIZE_TYPE__);
void *memset(void *, int, __SIZE_TYPE__);
int memcmp(const void *, const void *, __SIZE_TYPE__);
__SIZE_TYPE__ strlen(const char *);
int strcmp(const char *, const char *);
int strncmp(const char *, const char *, __SIZE_TYPE__);
char *strcpy(char *, const char *);
char *strncpy(char *, const char *, __SIZE_TYPE__);
#ifdef __cplusplus
}
#endif
