// 内核 libc 子集的 stdio.h。
// 只有格式化输出有意义：snprintf/vsnprintf 等由内核导出，printf 走 vprintk。
// FILE 和文件操作没有内核对应物，调用点直接编译报错。

#pragma once

#include <__lcpp_port.h>
#include <stdarg.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct _IO_FILE FILE;
typedef long fpos_t;

/* 标准流只为了 libc++ <cstdio> 能声明 using，不提供实现 */
extern FILE *stdin;
extern FILE *stdout;
extern FILE *stderr;

#define EOF (-1)
#define BUFSIZ 8192
#define FILENAME_MAX 4096
#define L_tmpnam 20
#define TMP_MAX 238328

#define SEEK_SET 0
#define SEEK_CUR 1
#define SEEK_END 2

#define _IOFBF 0
#define _IOLBF 1
#define _IONBF 2

/* 内核导出：格式化到内存 */
int snprintf(char *buf, size_t size, const char *format, ...);
int vsnprintf(char *buf, size_t size, const char *format, va_list args);
int sprintf(char *buf, const char *format, ...);
int vsprintf(char *buf, const char *format, va_list args);

/* libc_port.c 实现：直接写 printk */
int printf(const char *format, ...);
int vprintf(const char *format, va_list args);
int puts(const char *s);
int putchar(int c);
void perror(const char *s);

int remove(const char *path) LCPP_UNSUPPORTED("内核模块请用 filp_open/vfs_unlink");
int rename(const char *old_path, const char *new_path)
	LCPP_UNSUPPORTED("内核模块请用 vfs_rename");
FILE *tmpfile(void) LCPP_UNSUPPORTED("内核模块没有临时文件");
char *tmpnam(char *s) LCPP_UNSUPPORTED("内核模块没有临时文件");
int fclose(FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int fflush(FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
void setbuf(FILE *stream, char *buf) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int setvbuf(FILE *stream, char *buf, int mode, size_t size)
	LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int fprintf(FILE *stream, const char *format, ...)
	LCPP_UNSUPPORTED("内核模块里请用 printk 或 snprintf");
int fscanf(FILE *stream, const char *format, ...) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int sscanf(const char *s, const char *format, ...)
	LCPP_UNSUPPORTED("内核里请用 kstrtoint/kstrtouint 等解析函数");
int vfprintf(FILE *stream, const char *format, va_list args)
	LCPP_UNSUPPORTED("内核模块里请用 vprintk");
int vfscanf(FILE *stream, const char *format, va_list args) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int vsscanf(const char *s, const char *format, va_list args) LCPP_UNSUPPORTED("内核模块没有 scanf");
int fgetc(FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
char *fgets(char *s, int size, FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int fputc(int c, FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int fputs(const char *s, FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int getc(FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int getchar(void) LCPP_UNSUPPORTED("内核模块没有 stdin");
int putc(int c, FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int ungetc(int c, FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
size_t fread(void *ptr, size_t size, size_t count, FILE *stream)
	LCPP_UNSUPPORTED("内核模块请用 kernel_read");
size_t fwrite(const void *ptr, size_t size, size_t count, FILE *stream)
	LCPP_UNSUPPORTED("内核模块请用 kernel_write");
int fgetpos(FILE *stream, fpos_t *pos) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int fseek(FILE *stream, long offset, int whence) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int fsetpos(FILE *stream, const fpos_t *pos) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
long ftell(FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
void rewind(FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
void clearerr(FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int feof(FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
int ferror(FILE *stream) LCPP_UNSUPPORTED("内核模块没有 FILE 流");
FILE *fopen(const char *path, const char *mode)
	LCPP_UNSUPPORTED("内核模块请用 filp_open/kernel_read/kernel_write");
FILE *freopen(const char *path, const char *mode, FILE *stream)
	LCPP_UNSUPPORTED("内核模块没有 FILE 流");
char *gets(char *s) LCPP_UNSUPPORTED("gets 已废弃，内核模块没有 stdin");
int scanf(const char *format, ...) LCPP_UNSUPPORTED("内核模块没有 stdin");
int vscanf(const char *format, va_list args) LCPP_UNSUPPORTED("内核模块没有 stdin");

#ifdef __cplusplus
}
#endif
