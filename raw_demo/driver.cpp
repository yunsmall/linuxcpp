// SPDX-License-Identifier: GPL-2.0-only

// raw 类型示例：C 侧只有 module_init/module_exit，初始化和清理都由 C++ 写。

#include "linuxcpp.hpp"

static int raw_init(void)
{
	// 标准库在 <绑定命名空间>::std 下，默认就是 linuxcpp::std
	linuxcpp::std::mutex mutex;
	linuxcpp::std::vector<int> values;
	if (!mutex.ok() || !values.push_back(1))
		return -12;

	void *ptr = linuxcpp::lc_kmalloc(16);
	if (ptr == nullptr)
		return -12;
	linuxcpp::lc_kfree(ptr);
	return 0;
}

static void raw_exit(void)
{
}

LCPP_MODULE_RAW(raw_init, raw_exit)
