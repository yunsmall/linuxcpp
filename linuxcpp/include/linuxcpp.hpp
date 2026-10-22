// SPDX-License-Identifier: GPL-2.0-only

// linuxcpp 核心库：给用户模块提供的 C++ 设施。
// 只依赖生成的 bindings.hpp，不 include 任何内核头。

#pragma once

#include "bindings.hpp"
#include "config.hpp"
#include "module.hpp"
#include "placement_new.hpp"
#include "std/array.hpp"
#include "std/error.hpp"
#include "std/fixed_string.hpp"
#include "std/memory.hpp"
#include "std/mutex.hpp"
#include "std/scope_guard.hpp"
#include "std/span.hpp"
#include "std/string_view.hpp"
#include "std/vector.hpp"

// 生成的 ABI 镜像在 linuxcpp::abi；手写的 C++ 设备模型在 linuxcpp::model。
// 两套名字必须显式写命名空间，不做 using-directive 兼容。

// C++ 变参函数不能直接转发给 C 的 printk，核心库用 vprintk 做一层 thunk；
// 这里用模板把参数原样传过去，调用方式和 printk 一致
extern "C" void lc_printk(const char *fmt, ...);

namespace linuxcpp {

template <typename... Args>
inline void printk(const char *fmt, Args... args)
{
	lc_printk(fmt, args...);
}

}  // namespace linuxcpp

// 标准库实现在 linuxcpp/std/，命名空间固定为 linuxcpp::std。
// 设备封装在 device.hpp，按需 include。
