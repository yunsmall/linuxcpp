// SPDX-License-Identifier: GPL-2.0-only

// linuxcpp 核心库的运行时部分：把 C++ 的堆分配接到内核分配器上。

#include <stddef.h>

#include "bindings.hpp"
#include "placement_new.hpp"

extern "C" void lc_bug(void) __attribute__((noreturn));

#ifndef LCPP_USE_LIBCXX
// 纯虚函数被调用说明对象已经析构，或者类型转换有 bug。内核里没有异常可抛，
// 直接 BUG 留下调用栈。使用 libc++ 时由运行库的 runtime.cpp 提供同一入口。
extern "C" void __cxa_pure_virtual(void);

extern "C" void __cxa_pure_virtual(void)
{
	lc_bug();
}
#endif

// GCC 下 noexcept 让分配失败时把 nullptr 原样返回；clang 认为全局 operator new
// 的内置声明带 throw(bad_alloc)，替换版本再写 noexcept 会冲突，
// 而 -fno-exceptions 下 clang 失败时同样返回 nullptr，所以只在 GCC 下加
#if defined(__clang__)
#define LCPP_NEW_SPEC
#else
#define LCPP_NEW_SPEC noexcept
#endif

namespace {

// kmalloc 只保证 ARCH_KMALLOC_MINALIGN，普通 operator new 需要满足
// __STDCPP_DEFAULT_NEW_ALIGNMENT__。多分配一点，手工对齐，
// 原始 kmalloc 指针存在返回地址前一个 void* 里。
constexpr size_t kNewAlign = __STDCPP_DEFAULT_NEW_ALIGNMENT__;
// 下面的位运算对齐只对 2 的幂成立；主流 ABI 都是 2 的幂，这里把它钉死
static_assert((kNewAlign & (kNewAlign - 1)) == 0, "new 对齐必须是 2 的幂");

void *alloc_aligned(size_t size, size_t align)
{
	if (align < kNewAlign)
		align = kNewAlign;
	if ((align & (align - 1)) != 0)
		return nullptr;
	if (size == 0)
		size = 1;
	if (size > static_cast<size_t>(-1) - align - sizeof(void *))
		return nullptr;

	linuxcpp::abi::lc_might_sleep();
	void *raw = linuxcpp::abi::lc_kmalloc(size + align + sizeof(void *));
	if (raw == nullptr)
		return nullptr;

	size_t start = reinterpret_cast<size_t>(raw) + sizeof(void *);
	size_t aligned = (start + align - 1) & ~(align - 1);
	reinterpret_cast<void **>(aligned)[-1] = raw;
	return reinterpret_cast<void *>(aligned);
}

void free_aligned(void *ptr)
{
	if (ptr != nullptr)
		linuxcpp::abi::lc_kfree(reinterpret_cast<void **>(ptr)[-1]);
}

}  // namespace

#ifndef LCPP_USE_LIBCXX
// libc++ 模式的 std::nothrow 由运行库的 new_helpers.cpp 提供，不能重复定义
namespace std {
extern const nothrow_t nothrow{};
}  // namespace std
#endif

void *operator new(size_t size) LCPP_NEW_SPEC
{
	return alloc_aligned(size, kNewAlign);
}

void operator delete(void *ptr) noexcept
{
	free_aligned(ptr);
}

void operator delete(void *ptr, size_t) noexcept
{
	free_aligned(ptr);
}

void *operator new[](size_t size) LCPP_NEW_SPEC
{
	return alloc_aligned(size, kNewAlign);
}

void operator delete[](void *ptr) noexcept
{
	free_aligned(ptr);
}

void operator delete[](void *ptr, size_t) noexcept
{
	free_aligned(ptr);
}

// over-aligned 类型（包括 libc++ 的容器）会用 aligned new/delete；这些入口
// 必须和普通版本共用同一套记录原始指针的布局，否则析构时无法正确 kfree
void *operator new(size_t size, std::align_val_t alignment) LCPP_NEW_SPEC
{
	return alloc_aligned(size, static_cast<size_t>(alignment));
}

void *operator new[](size_t size, std::align_val_t alignment) LCPP_NEW_SPEC
{
	return alloc_aligned(size, static_cast<size_t>(alignment));
}

void operator delete(void *ptr, std::align_val_t) noexcept
{
	free_aligned(ptr);
}

void operator delete(void *ptr, size_t, std::align_val_t) noexcept
{
	free_aligned(ptr);
}

void operator delete[](void *ptr, std::align_val_t) noexcept
{
	free_aligned(ptr);
}

void operator delete[](void *ptr, size_t, std::align_val_t) noexcept
{
	free_aligned(ptr);
}

void *operator new(size_t size, const std::nothrow_t &) noexcept
{
	return alloc_aligned(size, kNewAlign);
}

void *operator new[](size_t size, const std::nothrow_t &) noexcept
{
	return alloc_aligned(size, kNewAlign);
}

void *operator new(size_t size, std::align_val_t alignment,
		   const std::nothrow_t &) noexcept
{
	return alloc_aligned(size, static_cast<size_t>(alignment));
}

void *operator new[](size_t size, std::align_val_t alignment,
		     const std::nothrow_t &) noexcept
{
	return alloc_aligned(size, static_cast<size_t>(alignment));
}

void operator delete(void *, const std::nothrow_t &) noexcept
{
}

void operator delete[](void *, const std::nothrow_t &) noexcept
{
}

void operator delete(void *, std::align_val_t, const std::nothrow_t &) noexcept
{
}

void operator delete[](void *, std::align_val_t, const std::nothrow_t &) noexcept
{
}

#undef LCPP_NEW_SPEC
