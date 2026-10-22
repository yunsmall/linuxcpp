// SPDX-License-Identifier: GPL-2.0-only

// 链接顺序上排在所有 .init_array/.fini_array 输入段之前。

__asm__(
	".section .init_array,\"aw\"\n"
	".global __lcpp_init_array_start\n"
	"__lcpp_init_array_start:\n"
	".previous\n"
	".section .fini_array,\"aw\"\n"
	".global __lcpp_fini_array_start\n"
	"__lcpp_fini_array_start:\n"
	".previous\n");
