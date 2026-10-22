// libc_port 公共标记：哪些接口在内核里根本不存在，哪些是弱定义。
// 静态头只放声明；真正跟内核/架构有关的类型和 errno 由 gen_libc_headers.py 生成。

#pragma once

#if defined(__clang__)
// clang 用 unavailable 更准确；调用点会直接报“不可用”
#define LCPP_UNSUPPORTED(msg) __attribute__((unavailable(msg)))
#else
// GCC 的 error 属性在调用点报错，报错信息里带上原因
#define LCPP_UNSUPPORTED(msg) __attribute__((error(msg)))
#endif

// 让用户可以在自己的模块里提供强定义覆盖默认实现
#define LCPP_WEAK __attribute__((weak))
