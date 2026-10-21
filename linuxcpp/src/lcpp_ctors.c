// SPDX-License-Identifier: GPL-3.0-or-later

// 内核不会自动运行 C++ 全局构造函数/析构函数，由 C 入口遍历 .init_array/.fini_array。

typedef void (*lcpp_init_fn)(void);

extern lcpp_init_fn __lcpp_init_array_start[];
extern lcpp_init_fn __lcpp_init_array_end[];
extern lcpp_init_fn __lcpp_fini_array_start[];
extern lcpp_init_fn __lcpp_fini_array_end[];

void lcpp_run_init_array(void)
{
	lcpp_init_fn *fn;

	for (fn = __lcpp_init_array_start; fn < __lcpp_init_array_end; ++fn)
		(*fn)();
}

void lcpp_run_fini_array(void)
{
	lcpp_init_fn *fn;

	for (fn = __lcpp_fini_array_end; fn > __lcpp_fini_array_start; --fn)
		(*(fn - 1))();
}
