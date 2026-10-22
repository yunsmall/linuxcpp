// 整数限值由 gen_libc_headers.py 从目标编译器内置宏生成，避免手写死 32/64 位。
// 生成目录排在静态头前面，include_next / 直接 include 都会先命中它。

#pragma once

#include <bits/limits.h>
