// SPDX-License-Identifier: GPL-3.0-or-later

// 模块入口和 THIS_MODULE 的 C++ 对应物。

#pragma once

#include "bindings.hpp"

// 对应 C 的 THIS_MODULE；file_operations.owner 直接用它
struct module;
extern "C" struct module __this_module;

namespace linuxcpp {

struct module;

inline module *this_module()
{
	return reinterpret_cast<module *>(&__this_module);
}

}  // namespace linuxcpp

// 任意模块：自己写 init/exit，里面可以注册 platform、chrdev、kthread 等任何东西。
// 生成的 C 入口会先运行 .init_array 再调 InitFn，ExitFn 之后逆序运行 .fini_array；
// InitFn 失败时入口也会逆序运行 .fini_array，所以这里不需要重复处理全局构造/析构。
#define LCPP_MODULE_RAW(InitFn, ExitFn)                                                            \
	extern "C" int lcpp_module_init(void);                                                     \
	extern "C" void lcpp_module_exit(void);                                                    \
	extern "C" int lcpp_module_init(void) { return InitFn(); }                                  \
	extern "C" void lcpp_module_exit(void) { ExitFn(); }
