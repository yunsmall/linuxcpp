// SPDX-License-Identifier: GPL-2.0-only

// libc++ 运行库里无法用普通 C 代码实现的部分。
// errno、strtol、strerror、atexit 已经移到 libc_port，这里只留 C++ ABI 入口。

#include <__config>
#include <__verbose_abort>
#include <cstdarg>
#include <cstddef>

extern "C" void lc_printk(const char *fmt, ...);
extern "C" void lc_bug(void) __attribute__((noreturn));
extern "C" int vsnprintf(char *buf, __SIZE_TYPE__ size, const char *fmt, va_list args);
extern "C" void __cxa_pure_virtual(void);

_LIBCPP_BEGIN_NAMESPACE_STD

void __libcpp_verbose_abort(char const *format, ...) _LIBCPP_VERBOSE_ABORT_NOEXCEPT
{
	va_list args;
	va_start(args, format);
	char buffer[512];
	vsnprintf(buffer, sizeof(buffer), format, args);
	va_end(args);
	lc_printk("libc++: %s", buffer);
	lc_bug();
}

_LIBCPP_END_NAMESPACE_STD

// 头文件里的 _LIBCPP_VERBOSE_ABORT 先调用这里打印，再用 __builtin_trap()
// 终止；声明故意不加 noreturn，objtool 才能看到后面的 ud2。
extern "C" void lcpp_log_abort(const char *format, ...) noexcept
{
	va_list args;
	va_start(args, format);
	char buffer[512];
	vsnprintf(buffer, sizeof(buffer), format, args);
	va_end(args);
	lc_printk("libc++: %s", buffer);
	lc_bug();
}

extern "C" void __cxa_pure_virtual(void)
{
	lc_bug();
}
