// SPDX-License-Identifier: GPL-2.0-only

// 内核线程示例：不注册设备，init/exit 里管理 kthread。

#include "linuxcpp.hpp"

// kthread_create_on_node 的参数里只有 task_struct 指针，前向声明即可
namespace linuxcpp {
struct task_struct;
}

static linuxcpp::abi::task_struct *g_task;

static int worker(void *data)
{
	(void)data;
	while (!linuxcpp::abi::kthread_should_stop())
		linuxcpp::abi::msleep(1000);
	return 0;
}

static int demo_init(void)
{
	g_task = linuxcpp::abi::kthread_create_on_node(worker, nullptr, -1, "linuxcpp_kthread");
	if (linuxcpp::std::is_error(g_task))
		return static_cast<int>(linuxcpp::std::ptr_error(g_task));
	linuxcpp::abi::wake_up_process(g_task);
	return 0;
}

static void demo_exit(void)
{
	if (g_task != nullptr)
		linuxcpp::abi::kthread_stop(g_task);
}

LCPP_MODULE_RAW(demo_init, demo_exit)
