// SPDX-License-Identifier: GPL-3.0-or-later

// placement new：内核不链接 libstdc++，这里提供最小实现。

#pragma once

#include <stddef.h>

// 编译器通常内置这个宏；没有时按 max_align_t 处理
#ifndef __STDCPP_DEFAULT_NEW_ALIGNMENT__
#define __STDCPP_DEFAULT_NEW_ALIGNMENT__ alignof(max_align_t)
#endif

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
