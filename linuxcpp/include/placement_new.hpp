// SPDX-License-Identifier: GPL-2.0-only

// placement new：非 libc++ 模块由这里提供最小实现；libc++ 模块直接用 <new>。

#pragma once

#include <stddef.h>

// 编译器通常内置这个宏；没有时按 max_align_t 处理
#ifndef __STDCPP_DEFAULT_NEW_ALIGNMENT__
#define __STDCPP_DEFAULT_NEW_ALIGNMENT__ alignof(max_align_t)
#endif

#ifdef LCPP_USE_LIBCXX

// libc++ 的 <new> 已经带了 placement new、align_val_t 和 nothrow_t
#include <new>

#else

// 不用 libc++ 时没有 <new>，但 C++17 的 alignas 类型仍会调用 aligned
// new/delete，nothrow 版本也需要类型；这里补上和标准布局一致的最小定义
namespace std {
enum class align_val_t : size_t {};
struct nothrow_t {
	explicit nothrow_t() = default;
};
extern const nothrow_t nothrow;
}  // namespace std

// 这些替换版本在 linuxcpp.cpp 里定义。没有 <new> 时编译器不会替它们
// 预声明，定义处会触发 -Wmissing-declarations，所以在这里补上。
void *operator new(size_t, const std::nothrow_t &) noexcept;
void *operator new[](size_t, const std::nothrow_t &) noexcept;
void *operator new(size_t, std::align_val_t, const std::nothrow_t &) noexcept;
void *operator new[](size_t, std::align_val_t, const std::nothrow_t &) noexcept;
void operator delete(void *, const std::nothrow_t &) noexcept;
void operator delete[](void *, const std::nothrow_t &) noexcept;
void operator delete(void *, std::align_val_t, const std::nothrow_t &) noexcept;
void operator delete[](void *, std::align_val_t, const std::nothrow_t &) noexcept;

// 内核模块用 -nostdinc，<new> 由 gen_libc_shim.py 生成的 shim 提供，两边共用
// 这个宏。真正的 libstdc++ <new> 不能出现在内核模块里，那种构建方式本身不成立。
#ifndef LCPP_PLACEMENT_NEW_DEFINED
#define LCPP_PLACEMENT_NEW_DEFINED
inline void *operator new(size_t, void *ptr) noexcept
{
	return ptr;
}

inline void *operator new[](size_t, void *ptr) noexcept
{
	return ptr;
}

inline void operator delete(void *, void *) noexcept
{
}

inline void operator delete[](void *, void *) noexcept
{
}
#endif

#endif
