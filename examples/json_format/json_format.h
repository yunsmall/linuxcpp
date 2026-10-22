// SPDX-License-Identifier: GPL-2.0-only

// 内核模块和用户态工具共用的 ioctl 命令。
// 参数是待格式化 JSON 文件的 fd，成功返回 0，失败返回 -errno。

#pragma once

#define LCPP_JSON_FORMAT 0x4A01

#ifdef __cplusplus
extern "C" {
#endif

// 解析并按两格缩进输出 JSON。output 为 NULL 时只返回所需长度；
// capacity 包含结尾 NUL 的空间。成功返回格式化长度，失败返回 -errno。
long lc_pretty_json(const char *input, unsigned long length,
		    char *output, unsigned long capacity);

#ifdef __cplusplus
}
#endif
