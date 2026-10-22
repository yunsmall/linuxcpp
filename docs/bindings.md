# 绑定与 API 分类

`module.toml` 的 `[bindings]` 决定生成器要为哪些内核类型和函数生成 C/C++ 声明。它只有五个列表，但每个列表对应内核 API 的不同存在形式，判断错会在链接期才暴露，所以这里单独说明。

```toml
[bindings]
roots = ["file", "file_operations", "kiocb", "iov_iter", "miscdevice"]
extern = ["misc_register", "misc_deregister", "compat_ptr_ioctl"]
thunk = ["copy_to_iter", "copy_from_iter", "copy_from_user", "copy_to_user"]
# macro = ["MAY_READ"]
# headers = ["linux/fs.h", "linux/sched.h"]
# packed = ["some_packed_struct"]
```

## roots：BTF 类型

`roots` 是需要完整定义的内核类型。生成器从 BTF 导出布局，再沿字段递归求依赖闭包：

- 按值使用的字段：生成完整结构体定义
- 只通过指针使用的类型：生成前向声明

所以通常只需要写入口类型，例如 `file`，`inode`、`dentry`、`path`、`file_operations` 会自动出现。只有 C++ 代码要访问字段、按值持有、或者需要 `sizeof` 时才必须放进 `roots`。

`roots` 里也可以写 enum 或 typedef 名，生成器会分别处理。名字在 BTF 里不存在时会打印警告并忽略。

## extern：内核导出函数

`extern` 用于 `EXPORT_SYMBOL`/`EXPORT_SYMBOL_GPL` 出来的函数。生成器从内核头里找到函数声明，生成 `extern "C"` 声明；链接时由内核或其他模块提供实现。

生成器会读 `$(KDIR)/Module.symvers` 检查符号是否真的导出。遇到以下情况会给出提示：

- 头文件里找不到声明：可能是函数宏，需要手写 C 包装
- 函数在头文件里有 `static inline` 定义：没有可链接的导出符号，应该放到 `thunk`
- 不在 `Module.symvers` 里：可能没有导出；如果来自自己的另一个 `.ko`，用 `KBUILD_EXTRA_SYMBOLS` 提供符号表

外部模块提供的符号不在内核的 `Module.symvers` 里，这种警告可以忽略，但要在 Makefile 里声明：

```make
KBUILD_EXTRA_SYMBOLS := $(LINUXCPP)/runtime/Module.symvers
```

## thunk：static inline 函数

`thunk` 用于头文件里 `static inline` 定义的函数。C++ 代码不能直接调用它们，因为 C++ 编译单元没有包含内核头；生成器会生成一个 C 包装函数（`thunks_gen.c`），由 kbuild 用内核头编译，再暴露给 C++。

例如 `copy_to_user` 是 `static inline`，适合放 `thunk`。生成器会检查：

- 找不到声明：可能是函数宏，只能在模块目录的 `.c` 文件里手写包装
- 只有声明、没有定义：不能生成 thunk；如果它其实是导出函数，应该放到 `extern`

`thunk` 生成的 C++ 函数名带 `lc_` 前缀，例如 `linuxcpp::abi::lc_copy_to_iter`。

## macro：对象宏

对象宏（`#define MAY_READ 0x4`）没有参数，预处理器展开后就是一个表达式，可以自动导出成 `inline constexpr auto`；用 `macro = [...]` 指定，常用 errno 默认导出。

函数宏（`_IOW`、`copy_to_user`、`container_of`、`pr_info`）在预处理阶段做 token 替换，依赖 `typeof`、语句表达式、`#`/`##`、参数多次求值，AST 里没有它们的函数语义，不能可靠自动翻译。处理方式：

- 能包成普通函数的，写进 `thunk`，生成器生成 C 包装（`copy_to_user` 就是）
- 纯计算/常量组合的，用 `constexpr` 重写（`ioctl_misc` 示例里的 `_IOC`）
- 依赖内核内部符号或特殊语句的，手写 C thunk，放进模块目录的 `.c` 文件（构建器会编译并链接）

## headers：解析用的内核头

`headers` 是解析 `extern`、`thunk` 和 `macro` 时额外 include 的内核头，默认已经包含一组常用头（`linux/module.h`、`linux/fs.h`、`linux/miscdevice.h`、`linux/uio.h`、`linux/slab.h`、`linux/uaccess.h`）。

如果某个函数或宏在别的头里，把它加进来，例如：

```toml
headers = ["linux/completion.h", "linux/spinlock.h", "linux/atomic.h"]
```

## packed：强制 packed

bpftool 生成 `vmlinux.h` 时会漏掉部分 `__packed`/`aligned` 属性。生成器会按 BTF 的 size 和 bit offset 自动重建，但遇到无法自动判断的类型，可以用 `packed = ["类型名"]` 强制加 `packed`。

## 怎么判断一个内核 API 属于哪类

```bash
# 导出函数 → extern
grep -r "EXPORT_SYMBOL.*my_func" /path/to/kernel

# static inline → thunk
grep -rn "static inline.*my_func" /path/to/kernel/include

# 对象宏（无参数）→ macro
grep -rn "#define MY_CONST" /path/to/kernel/include

# 函数宏 → 手写 thunk 或 constexpr
grep -rn "#define my_func(" /path/to/kernel/include
```

结构体：C++ 要访问字段时加到 `roots`；只传指针的话不用加，生成器会给前向声明。

## 生成器诊断

绑定生成阶段会打印以 `警告：` 开头的提示，常见的有：

| 提示 | 含义和处理 |
|---|---|
| `roots 里的 X 在 BTF 中没有对应类型` | 名字拼错，或该类型不在 BTF 里 |
| `extern 里的 X 找不到函数声明` | 可能是函数宏；在模块的 `.c` 文件里手写包装 |
| `extern 里的 X 是 static inline 定义` | 没有导出符号；把 X 移到 `thunk` |
| `extern 里的 X 不在 Module.symvers 中` | 可能没有导出；如果来自外部模块，用 `KBUILD_EXTRA_SYMBOLS` |
| `thunk 里的 X 找不到函数声明` | 可能是函数宏；手写 C 包装 |
| `thunk 里的 X 是导出函数，没有内联定义` | 把 X 移到 `extern` |
| `thunk 里的 X 在头文件里没有定义` | 不能生成 thunk；检查是否该放 `extern` 或手写 |

这些检查依赖 `/lib/modules/$(uname -r)/build/Module.symvers`。如果该文件不存在，导出检查会跳过，只保留声明检查。
