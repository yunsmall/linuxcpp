// SPDX-License-Identifier: GPL-2.0-only

// 给 C++ 侧提供最小的 FPU 区间入口。这个翻译单元不编译浮点代码。

#include <linux/module.h>
#include <asm/fpu/api.h>

void lc_fpu_begin(void);
void lc_fpu_end(void);

void lc_fpu_begin(void)
{
	kernel_fpu_begin();
}

void lc_fpu_end(void)
{
	kernel_fpu_end();
}
