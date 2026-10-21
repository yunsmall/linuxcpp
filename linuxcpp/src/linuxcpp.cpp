// SPDX-License-Identifier: GPL-3.0-or-later

// linuxcpp 核心库的运行时部分：把 C++ 的堆分配接到内核分配器上。

#include <stddef.h>

#include "bindings.hpp"
#include "placement_new.hpp"

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

void *alloc_aligned(size_t size)
{
	if (size == 0)
		size = 1;
	if (size > static_cast<size_t>(-1) - kNewAlign - sizeof(void *))
		return nullptr;

	void *raw = linuxcpp::lc_kmalloc(size + kNewAlign + sizeof(void *));
	if (raw == nullptr)
		return nullptr;

	size_t start = reinterpret_cast<size_t>(raw) + sizeof(void *);
	size_t aligned = (start + kNewAlign - 1) & ~(kNewAlign - 1);
	reinterpret_cast<void **>(aligned)[-1] = raw;
	return reinterpret_cast<void *>(aligned);
}

void free_aligned(void *ptr)
{
	if (ptr != nullptr)
		linuxcpp::lc_kfree(reinterpret_cast<void **>(ptr)[-1]);
}

}  // namespace

void *operator new(size_t size) LCPP_NEW_SPEC
{
	return alloc_aligned(size);
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
	return alloc_aligned(size);
}

void operator delete[](void *ptr) noexcept
{
	free_aligned(ptr);
}

void operator delete[](void *ptr, size_t) noexcept
{
	free_aligned(ptr);
}

#undef LCPP_NEW_SPEC
