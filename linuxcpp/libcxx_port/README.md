# libc++ 20.1.8（内核移植）

- 上游：<https://github.com/llvm/llvm-project>，tag `llvmorg-20.1.8`
- 许可证：Apache-2.0 WITH LLVM-exception，见 `LICENSE.TXT`
- 保留 `include/`（去掉了冻结的 C++03 头 `__cxx03`）和完整的 `src/`
- 下载脚本：`update_libcxx.py`，固定 URL、SHA256，自动应用 `patches/`，安装到仓库根 `third_party/libcxx/`

libc++ 不随仓库分发。LLVM 现在只有 llvm-project 单一仓库，作为 submodule 会拉下整个项目，体积太大；独立的 libcxx 镜像又停留在很老的版本。所以由脚本按需下载内核需要的头文件和运行库源码到 `third_party/libcxx/`，该目录在 `.gitignore` 里。

## 对上游的修改

1. `include/errno.h`：定义 `_LIBCPP_ERRNO_DEFINED_BY_PORT` 时跳过它给缺失 errno 补宏的代码。内核移植用 enum 提供错误码，否则 `linuxcpp::abi::EFAULT` 这类标识符会被宏替换。
2. `include/__hash_table`：去掉 `max_load_factor()` 相关的浮点乘法/除法，桶数按负载因子 1.0 计算，`reserve` 直接使用请求的桶数。自定义 `max_load_factor` 在内核里不生效，但容器仍然正确。
3. 浮点入口不在下载目录：`linuxcpp/libcxx_port/src/string.cpp` 和 `algorithm.cpp` 是从上游复制后去掉 `stof/stod/stold`、浮点 `to_string` 和 float/double/long double 的 `__sort` 实例化。内核不保存 FPU/SSE 状态，`-mno-sse -mno-80387` 下不能生成浮点代码。

补丁位于 `patches/`，`update_libcxx.py` 会在解压后按文件名顺序应用。

## 内核移植层

- `linuxcpp/libcxx_port/include/__config_site`：关闭线程、locale、filesystem、宽字符、随机设备等
- `linuxcpp/libcxx_port/include/__assertion_handler`：来自上游 `vendor/llvm/default_assertion_handler.in`
- `linuxcpp/libcxx_port/src/runtime.cpp`：只保留 `__libcpp_verbose_abort` 和 C++ ABI 入口
- `linuxcpp/libc_port/`：内核 C 库子集，libc++ 和其他模块共用；`errno`/类型头按目标内核生成
- `linuxcpp/src/linuxcpp.cpp`：`operator new/delete` 以及 aligned/nothrow 版本，全部走 kmalloc/kfree

运行库由 `linuxcpp/runtime/Makefile` 编成独立的 `libcxx_runtime.ko`，`linuxcpp/python/gen_libcxx_exports.py` 从对象文件生成 `EXPORT_SYMBOL_GPL` 表。使用它的模块 include `linuxcpp/libcxx.mk`，并设置 `KBUILD_EXTRA_SYMBOLS` 指向 `linuxcpp/runtime/Module.symvers`。

## C 头 shim 和 include 顺序

libc++ 的 `<cstdlib>`、`<cstring>`、`<cstdio>` 不会直接包含系统 C 头：它们先找 libc++ 自己的 `stdlib.h`/`string.h` 包装头，包装头再 `#include_next` 到平台 C 头。内核没有 libc，`linuxcpp/libc_port/include` 就是这层平台头；这些文件不是给用户直接 include 的。

C++ 编译 flags 的顺序必须是：

```text
-nostdinc++                                  # 屏蔽宿主 libstdc++
-I linuxcpp/libcxx_port/include              # __config_site / __assertion_handler
-I third_party/libcxx/include                # libc++ 头 + C 包装头
-I <模块>/generated/libc_port/include        # 目标内核生成的 errno/types
-I linuxcpp/libc_port/include                # include_next 落到的静态 C 头
```

各 C 头的边界：

| 头文件 | 内容 |
|---|---|
| `<模块>/generated/libc_port/include/errno.h` | 从目标内核 `<asm/errno.h>` 生成 enum 错误码 |
| `<模块>/generated/libc_port/include/bits/types.h` | `time_t`/`ssize_t`/`clock_t`，来自编译器内置宏 |
| `string.h` | `memcpy/strlen` 等内核导出声明，`strerror/strdup/strndup` 由 libc_port 实现 |
| `stdlib.h` / `stdio.h` / `time.h` | malloc/qsort/printf/time 子集；不支持的文件流、环境变量、locale 等编译期报错 |
| `ctype.h` / `assert.h` | 内核可用的内联实现 |
| `math.h` | 分类宏；浮点函数没有实现 |

`strtol/strtoll/strtoul/strtoull`、`__errno_location` 和 `atexit` shim 在 `linuxcpp/libc_port/src/libc_port.c`；`memcpy`、`snprintf`、`vsnprintf`、`bsearch` 等直接使用内核导出符号。
