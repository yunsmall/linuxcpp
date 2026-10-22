// 内核没有 __assert_fail，直接 trap；断言失败会停在出错的指令上。

#pragma once

#define assert(expr) ((expr) ? (void)0 : __builtin_trap())
