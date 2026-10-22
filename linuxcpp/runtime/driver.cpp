// SPDX-License-Identifier: GPL-2.0-only

// libc++ 共享运行库模块。它只负责被加载和导出符号，不注册设备。

#include "linuxcpp.hpp"

namespace {

int runtime_init(void)
{
	linuxcpp::printk("libcxx_runtime: init\n");
	return 0;
}

void runtime_exit(void)
{
	linuxcpp::printk("libcxx_runtime: exit\n");
}

}  // namespace

LCPP_MODULE_RAW(runtime_init, runtime_exit)
