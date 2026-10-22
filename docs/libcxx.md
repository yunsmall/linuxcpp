# libc++（可选）

内核版 libc++ 不是模块构建模式，而是一个普通模块：`linuxcpp/runtime/libcxx_runtime.ko`。它把 libc++ 运行库源码编进自己的 `.ko`，导出需要的 C++ 符号；其他模块像依赖任何外部模块一样，通过 `KBUILD_EXTRA_SYMBOLS` 使用它的 `Module.symvers`。

## 下载 libc++ 源码

libc++ 不随仓库分发，第一次使用前在仓库根目录执行：

```bash
python3 linuxcpp/libcxx_port/update_libcxx.py
```

脚本从固定 URL 下载 libc++ 20.1.8、校验 SHA256，解压到仓库根的
`third_party/libcxx/`（已被 `.gitignore` 忽略），并应用 `linuxcpp/libcxx_port/patches/`
下的内核补丁。需要走代理时设置 `HTTPS_PROXY`，例如
`HTTPS_PROXY=http://127.0.0.1:7897 python3 linuxcpp/libcxx_port/update_libcxx.py`。

## 构建和加载运行库

```bash
make runtime
sudo insmod linuxcpp/runtime/libcxx_runtime.ko
```

`make runtime` 等价于 `make -C linuxcpp/runtime -j6`。运行库只注册 init/exit，不创建设备；加载后 `lsmod` 里能看到其他模块对它的依赖：

```text
libcxx_runtime        5.4M  2 std_demo,ctre_demo
```

使用 libc++ 的模块必须先加载 `libcxx_runtime.ko`，否则 `insmod` 会报未知符号。

## 已验证的标准库设施

在 `6.18.33.1-microsoft-standard-WSL2` 上，`examples/std_demo` 会实际运行下面这些设施：

- 容器：`vector`、`map`、`set`、`unordered_map`、`unordered_set`、`list`、`deque`、`forward_list`
- `optional`、`variant`、`any`、`span`、`string_view`
- `shared_ptr`、`unique_ptr`、`function`、`error_code`/`system_error`
- `array`、`tuple`、`bitset`、`accumulate`、`atomic` 的基本操作
- `ranges` 的 `sort`/`find`
- `charconv` 的整数 `to_chars`/`from_chars`
- `chrono`：`system_clock::now`/`to_time_t`/`from_time_t`、`steady_clock::now`

`chrono` 的时间源是内核时钟：`libcxx_port/src/chrono.cpp` 调用 `libc_port.c` 里的
`lc_ktime_get_real_ns`/`lc_ktime_get_monotonic_ns`，不经过 `clock_gettime`。

暂不支持：iostream/sstream/fstream、filesystem 操作、thread/mutex/future、regex，
以及浮点格式化和浮点 `charconv`（内核模块不保存 FPU 状态）。

## 在模块里使用

模块自己的 Makefile 加上两件事：

```make
include $(LINUXCPP)/libcxx.mk
KBUILD_EXTRA_SYMBOLS := $(LINUXCPP)/runtime/Module.symvers
```

`libcxx.mk` 只追加编译参数，不改变构建模式：

```text
-nostdinc++                                  # 不要宿主 libstdc++
-DLCPP_USE_LIBCXX                            # linuxcpp 核心库改用 libc++ 的 <new>
-I linuxcpp/libcxx_port/include              # __config_site / __assertion_handler
-I third_party/libcxx/include                # libc++ 头 + 它自己的 C 包装头（自行下载）
-I <模块>/generated/libc_port/include        # 按目标内核/架构生成的 errno/types
-I linuxcpp/libc_port/include                # 静态 C 头，include_next 落在这里
```

如果模块是用 `build.py --init` 创建的，Makefile 里已经留了注释，取消这两行即可：

```make
# include $(LINUXCPP)/libcxx.mk
# KBUILD_EXTRA_SYMBOLS := $(LINUXCPP)/runtime/Module.symvers
```

Makefile 只在缺失时由 `build.py` 初始化一次，之后归用户维护；把上面的行加进 `$(LINUXCPP_BUILD)` 分支即可。新增源文件同样直接加到 `<模块名>-y`。

不使用共享运行库时，也可以在模块 Makefile 里设置 `LCPP_LIBCXX := 1`，把运行库源码直接编进当前模块；这样每个模块都会增大几 MB，通常只在调试运行库本身时有用。

## 能用的部分

- `std::vector`、`std::array`、`std::span`、`std::string`、`std::string_view`、`std::optional`、`std::variant`
- `<algorithm>`（整数和用户类型；浮点排序实例化已移除）、`<utility>`、`<tuple>`、`<type_traits>`、`<bit>`
- `std::unique_ptr`、`std::shared_ptr`、`std::atomic`（基本操作）、`std::unordered_map`（负载因子按 1.0 处理）
- `std::to_string` 的整数版本
- `std::error_code`/`std::system_error` 的查询部分；没有异常抛出路径

## 不能用的部分

- 异常、RTTI：仍然是 `-fno-exceptions -fno-rtti`
- `std::thread`、`std::mutex`、`std::condition_variable`：用内核的 kthread/mutex/completion 包装
- `iostream`、`filesystem`、`locale`、`random_device`、宽字符（`wstring`/`wstring_view`）
- 浮点：`std::stof/stod/stold`、`to_string(float/double/long double)` 和浮点 `std::sort` 实例化都被移除。内核不保存 FPU/SSE 状态，`-mno-sse -mno-80387` 下也不应该生成浮点代码
- `std::atomic::wait/notify_one/notify_all`：`atomic.cpp` 用 futex `syscall` 实现，内核模块里没有该系统调用，所以没有编进运行库

## 版本和更新

当前固定 **libc++ 20.1.8**：21/22/23 的 type traits 依赖 GCC 15 或 Clang 19+ 的内置 trait，而这里的内核 C++ 编译器是 GCC 14。

下载或更新源码：

```bash
python3 linuxcpp/libcxx_port/update_libcxx.py
```

脚本从固定 URL 下载、校验 SHA256，只解压 `include/`、`src/` 和 `LICENSE.TXT`，删除 `__cxx03` 和 `__config_site.in`，应用 `patches/` 下的补丁，再替换 `third_party/libcxx/`。补丁和版本说明见 `linuxcpp/libcxx_port/README.md`。libc++ 本身仍按 Apache-2.0 WITH LLVM-exception 授权。

## 目录和 C 头文件

| 路径 | 作用 |
|---|---|
| `linuxcpp/libc_port/include/` | 内核 C 库子集的静态头：函数声明、不可用标记、编译器内置类型 |
| `<模块>/generated/libc_port/include/` | 按目标内核/编译器生成的 `errno.h`、`bits/types.h`、`bits/limits.h` |
| `linuxcpp/libc_port/src/libc_port.c` | C 子集实现：malloc/qsort/strtol/printf/time 等，全部是 weak 局部定义 |
| `linuxcpp/libcxx_port/include/` | libc++ 编译配置：`__config_site` 关闭宿主功能，`__assertion_handler` 来自上游 vendor |
| `third_party/libcxx/include/` | 自行下载的 libc++ 20.1.8 头文件；只改了 `errno.h` 和 `__hash_table`（不入库） |
| `third_party/libcxx/src/` | 上游完整运行库源码（不入库） |
| `linuxcpp/libcxx_port/src/` | 去浮点的 `string.cpp`/`algorithm.cpp`，以及只留 abort/C++ ABI 的 `runtime.cpp` |
| `linuxcpp/runtime/` | `libcxx_runtime.ko` 模块和手写 Makefile |
| `linuxcpp/python/gen_libc_headers.py` | 从目标内核和编译器生成 errno/类型头 |
| `linuxcpp/python/gen_libcxx_exports.py` | 从运行库对象收集全局符号，生成 `EXPORT_SYMBOL_GPL` 表 |

libc++ 的 `<cstdlib>`、`<cstring>`、`<cstdio>` 这类 C++ 头不会直接 include 系统 C 头：它们先找 libc++ 自己的 `stdlib.h`/`string.h` 包装头，再由包装头 `#include_next` 到平台 C 头。内核里没有 libc，所以用 `libc_port/include` 提供这层平台头。

`libc_port` 里每个头文件的内容和边界：

| 头文件 | 内容 |
|---|---|
| `<模块>/generated/libc_port/include/errno.h` | 从目标内核 `<asm/errno.h>` 生成 enum 错误码，避免宏替换 `linuxcpp::abi::EFAULT` |
| `<模块>/generated/libc_port/include/bits/types.h` | `time_t`/`ssize_t`/`clock_t`/`wint_t`，来自编译器内置宏 |
| `<模块>/generated/libc_port/include/bits/limits.h` | 整数限值，来自编译器内置宏，按目标架构生成 |
| `string.h` | `memcpy/strlen` 等内核导出声明，`strerror/strdup/strndup` 由 libc_port 实现；locale 相关标成不可用 |
| `stdlib.h` / `stdio.h` / `time.h` | 支持 malloc/qsort/printf/time 等子集；文件流、环境变量、locale、宽字符等调用点直接编译报错 |
| `ctype.h` / `assert.h` | 内核可用的内联实现 |
| `math.h` | 只保留分类宏；浮点函数没有实现，内核也不应该用 |

`libc_port/src/libc_port.c` 实现 `malloc/free/calloc/realloc`、`qsort`、`strtol/atoi`、`strerror`、`printf/vprintf`、`time/timespec_get`、`atexit` 等；`memcpy`、`snprintf`、`vsnprintf`、`bsearch` 等直接用内核导出的符号。未实现的函数在头文件里带 `LCPP_UNSUPPORTED`，调用时直接编译报错，不会拖到链接期。

运行库用 `atexit` 的空实现阻止 `generic_category`/`system_category` 的静态对象注册析构：内核模块里的静态对象本来就不应该在卸载时销毁。

## CTRE（可选，需自行下载）

CTRE（编译期正则）不随仓库分发，需要时在仓库根目录 clone：

```bash
git clone --depth 1 --branch v3.11.0 \
    https://github.com/hanickadot/compile-time-regular-expressions.git \
    third_party/ctre
```

把 clone 后 CTRE 的 `include` 路径加进 `module.toml`（路径相对模块目录，
`examples/` 或 `tmp/` 下的模块用 `../../third_party/ctre/include`）：

```toml
[build]
cxx_includes = ["../../third_party/ctre/include"]
```

也可以直接写进模块 Makefile：

```make
cxxflags-y += -I<path-to-ctre>/include
include $(LINUXCPP)/libcxx.mk
KBUILD_EXTRA_SYMBOLS := $(LINUXCPP)/runtime/Module.symvers
```

内核入口仍然用仓库里的 `linuxcpp/include/ctre_kernel.hpp`，它会补上 CTRE 需要的 `std::wstring_view` 占位类型。

```cpp
#include "ctre_kernel.hpp"

static_assert(ctre::match<"h.*o">("hello"));
auto matched = ctre::match<"([a-z]+)-(\\d+)">("abc-123");
if (matched) {
    // matched.get<1>() / matched.get<2>() 是 std::string_view
}
```

`examples/std_demo` 是标准库覆盖面验证模块；`tmp/ctre_demo` 是本地验证模块（`tmp/` 在 `.gitignore` 里）。`tmp/ctre_demo` 从仓库根的 `third_party/ctre` 取头文件，先按上面的命令 clone，再 `make -C tmp/ctre_demo`，最后按顺序 `insmod libcxx_runtime.ko`、`insmod ctre_demo.ko`。
