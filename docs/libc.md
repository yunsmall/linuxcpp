# 内核 C 库子集（libc_port）

`libc_port` 不是完整 libc，也不是一个独立的 `libc.ko`。它是一个按模块编译的小型 C 兼容层：

- `linuxcpp/libc_port/include/`：用户可见的静态头，只放声明和不可用标记；
- `<模块>/generated/libc_port/include/`：构建时按目标内核/编译器生成的 `errno.h`、`bits/types.h`、`bits/limits.h`；
- `linuxcpp/libc_port/src/libc_port.c`：实现，复制到每个模块目录并用 kbuild 编译成 `libc_port.o`。

`libc_port.o` 和 libc++ 无关。用不用 libc++，每个模块都会带这一份实现；区别只是头文件通过 `libc.mk` 暴露。

## 使用方式

### 不用 libc++

生成的 Makefile 默认已经包含：

```make
include $(LINUXCPP)/libc.mk
```

然后直接 include 标准头：

```cpp
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int init(void)
{
    char *p = static_cast<char *>(malloc(64));
    snprintf(p, 64, "value=%ld", strtol("123", nullptr, 10));
    printf("%s\n", p);
    free(p);
    return 0;
}
```

`examples/libc_demo` 是一个不用 libc++、实际调用 `malloc/calloc/realloc/free`、`qsort`、`bsearch`、`strtol`、`snprintf`、`printf`、`time` 的完整示例。

### 用 libc++

`libcxx.mk` 会自动 include `libc.mk`，因为 libc++ 的 C++ 头需要 C 头作为 `include_next` 落点。模块 Makefile 只需要：

```make
include $(LINUXCPP)/libcxx.mk
KBUILD_EXTRA_SYMBOLS := $(LINUXCPP)/runtime/Module.symvers
```

## 为什么按模块编译，而不是 libc.ko

- C 子集很小，重复一份比多一个模块加载顺序简单；
- 每个模块的 `errno` 独立，不会互相抢；
- 函数是 weak、不导出，内核将来自己导出同名符号时不会和模块符号表冲突；
- 不用 libc++ 的模块也能直接用，不需要先 `insmod libc.ko`。

如果以后子集明显变大，再考虑拆成独立 `libc.ko`，只导出内核没有的符号，并让消费者设置 `KBUILD_EXTRA_SYMBOLS`。

## 哪些函数能用

分三类。具体列表以 `libc_port.c` 和头文件为准。

### 内核已经导出，直接链接

`memcpy`、`memmove`、`memset`、`memcmp`、`memchr`、`strlen`、`strnlen`、`strcpy`、`strncpy`、`strcat`、`strncat`、`strcmp`、`strncmp`、`strchr`、`strrchr`、`strstr`、`strspn`、`strcspn`、`strpbrk`、`snprintf`、`vsnprintf`、`sprintf`、`vsprintf`、`bsearch`、`kstrdup`、`_ctype`。

这些不是每个内核版本都完全一样；构建时以 `Module.symvers` 为准。

### `libc_port.c` 自己实现（weak）

- 堆：`malloc`、`free`、`calloc`、`realloc`，最终走 `kmalloc/kfree/kzalloc/krealloc`；
- 字符串：`strerror`、`strdup`、`strndup`；
- 转换：`strtol/strtoll/strtoul/strtoull`、`atoi/atol/atoll`；
- 排序：`qsort`，自带 heapsort，不依赖内核 `sort()` 的签名；
- 输出：`printf/vprintf/puts/putchar/perror`，走 `vprintk`；
- 时间：`time`、`timespec_get`；
- 其他：`atexit`（空实现）。`abort` 直接使用内核导出的版本（`BUG()`/`panic()`）。

`qsort` 的 comparator 和标准一致；`printf` 只支持内核 `vprintk` 支持的格式，不要用浮点格式化。

### 明确不支持，调用点编译报错

`fopen/fclose/fread/fwrite/fseek`、`FILE` 流、`scanf` 系列、`getenv/system/exit/_Exit`、`localtime/gmtime/strftime/mktime`、宽字符/多字节、浮点 math、`strtok`、`strcoll/strxfrm`、`rand/srand`、`aligned_alloc` 等。

头文件里通过：

```c
#define LCPP_UNSUPPORTED(msg) __attribute__((error(msg)))
```

标在声明上；调用时直接报错，比如：

```text
error: call to 'fopen' declared with attribute error:
       kernel 模块里没有 fopen，请用 filp_open
```

GCC 用 `error` 属性，clang 用 `unavailable` 属性。

## 头文件怎么生成

跟架构有关的类型和错误码不手写：

- `errno.h`：用目标编译器预处理 `<asm/errno.h>`，从 `#define E...` 输出生成 enum；
- `bits/types.h`：从编译器内置宏生成 `ssize_t`（`__PTRDIFF_TYPE__`）、`time_t`（`__INT64_TYPE__`）、`clock_t`、`wint_t`；
- `bits/limits.h`：从 `__SCHAR_MAX__`、`__LONG_MAX__` 等生成，并带 `#ifndef` 保护；
- `libc_port.c` 里用 `_Static_assert` 对比 `struct timespec` 和内核 `struct timespec64` 的大小/偏移。

生成发生在 `build.py` 的 prepare 阶段，输出到模块自己的 `generated/libc_port/include`。换架构或换内核时不需要手改头文件。

## include 顺序

`libc.mk` 添加：

```text
-I <模块>/generated/libc_port/include
-I linuxcpp/libc_port/include
```

libc++ 模式下，`libcxx.mk` 把 libc++ 的 include 放在 `LCPP_LIBCXX_PREFLAGS` 里，排在所有 `ccflags-y/cxxflags-y` 之前：

```text
-nostdinc++
-I linuxcpp/libcxx_port/include
-I third_party/libcxx/include
-I <模块>/generated/libc_port/include
-I linuxcpp/libc_port/include
```

这样 `<cstdlib>` 会先找到 libc++ 自己的 `stdlib.h` 包装头，包装头的 `#include_next` 再落到 libc_port 的静态头。

## 和内核头文件的关系

**不要在同一个 `.c`/`.cpp` 文件里同时 include 内核头和 libc_port 头。**

- 内核头是 C 专用，C++ 解析不了；
- `linux/errno.h` 的 `EINVAL` 是宏，libc_port 的 `EINVAL` 是 enum，同时出现会互相替换；
- `linux/time.h` 的 `struct timespec` 和 libc_port 的 64 位 `time_t` 布局不同；
- `linux/string.h`、`linux/kernel.h` 里的 `abs/min/max` 等宏和 libc 声明会打架。

正确用法：

- **C++ 文件**：用 `linuxcpp.hpp`/`bindings.hpp` + libc_port 头，不碰内核头；
- **C thunk**：用内核头（`<linux/slab.h>`、`<linux/string.h>`、`<linux/errno.h>`），用 `kmalloc/printk/strlen`；不要在这个文件里 include libc_port 头；
- 需要新的内核 API：加进 `module.toml` 的 `[bindings]`，或者写 C thunk。

## weak 和未来内核导出

`libc_port.c` 里所有实现都是：

```c
__attribute__((weak))
```

目的：

1. 用户可以在自己的模块里提供同名强定义覆盖默认实现；
2. 这些符号不导出，内核将来自己导出 `malloc`/`qsort` 等功能时，不会和模块内部的 weak 定义抢符号表。

`build.py` 会拿 `libc_symbols.py` 里的实现列表和内核 `Module.symvers` 对比；如果内核已经导出同名符号，会在 prepare 阶段打印警告，提醒你可以改用内核实现。

## errno 的限制

`__errno_location()` 返回 per-CPU 变量，不是 POSIX 的 per-thread errno。内核代码应该用负错误码返回值（`-EINVAL`）而不是 errno；errno 只用于兼容 libc/libc++ 的同步检查。不要在可能迁移 CPU 的长时间操作中依赖同一个 errno。
