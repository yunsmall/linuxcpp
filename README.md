# linuxcpp：用 C++ 写 Linux 内核模块

linuxcpp 是一套工具链：你只写一个 `module.toml` 和一个 C++ 文件，就能编译出可加载的 Linux 内核模块。类型绑定、函数声明、C 入口、Kbuild、布局校验全部自动生成。

## 为什么不能直接 include 内核头

C++ 编译器解析内核头会失败，原因是两类：

- 关键字冲突：`struct class`、字段名 `private`、宏参数名 `not`（C++ 的替代运算符）
- C 专用语法：`typeof`、复合字面量、designated initializers、`_Generic`、`__builtin_types_compatible_p`、语句表达式

所以 linuxcpp 把工作拆成三层：

```
BTF (bpftool)            → 类型布局 → C/C++ 结构体镜像 + static_assert 校验
内核头 (libclang AST)     → 导出函数声明、static inline 的 C thunk
核心库 (linuxcpp_thunks.c)    → 宏和初始化函数的手写 thunk
```

C++ 代码只 include `linuxcpp.hpp`（需要 `Device` 时再 include `device.hpp`）和生成的 `bindings.hpp`，完全不碰内核头。

## 目录结构

```
test_rust/
├── linuxcpp/
│   ├── include/                公开 C++ 头（linuxcpp.hpp/module.hpp/device.hpp/std/wrappers）
│   ├── src/                    C/C++ 实现（linuxcpp.cpp/device.cpp/linuxcpp_thunks.c）
│   ├── python/                 构建和绑定生成脚本
│   │   ├── build.py            模块构建器
│   │   ├── gen_bindings.py     绑定生成器 CLI
│   │   ├── gen_libc_shim.py    freestanding 标准头生成器
│   │   ├── raw_top.c.in        C 入口模板（只有 module_init/exit）
│   │   └── linuxcppgen/        生成器实现（btf/deps/types/decls/codegen）
│   └── third_party/etl/        ETL 头与 shim
├── template/                   最小模块模板（misc 设备）
├── examples/                   可编译示例
│   ├── hello_misc              最小 misc 设备
│   ├── ioctl_misc              ioctl + 用户态拷贝 + 锁
│   ├── two_devices             一个模块两个设备
│   ├── kthread_demo            内核线程
│   └── etl_kv                  ETL 固定容量键值存储
├── raw_demo/                   raw 类型示例（不注册设备）
└── README.md
```

## 依赖

- Linux 内核头或源码树（`/lib/modules/$(uname -r)/build`）
- Python 3.11+（`tomllib`）
- libclang Python 绑定：`apt install python3-clang-22`
- `bpftool`（真实二进制；如果系统 wrapper 找不到自编内核，脚本会自动扫 `/usr/lib/linux-tools/*/bpftool`）
- C++ 编译器：默认跟随 kbuild 的 C 编译器（GCC → `g++`，clang → `clang++`），
  也可以在 `module.toml` 的 `[build] cxx` 里指定
- 内核开启 `CONFIG_MODULES`，最好有 `CONFIG_DEBUG_INFO_BTF`

## 快速开始

```bash
cp -r template mymodule
cd mymodule

# 改 module.toml 和 driver.cpp

python3 ../linuxcpp/python/build.py .   # 首次生成 Makefile/绑定并编译
make -j6                                # 之后直接增量构建

sudo insmod mymodule.ko
cat /dev/mymodule
sudo rmmod mymodule
```

第一次运行会生成 `Makefile`、`Kbuild`、`generated/` 和 `generated/cxxflags.mk`；之后在模块目录直接
`make -j6` 即可。Makefile 用 `-MMD -MP` 跟踪头文件依赖，C++ 对象和 kbuild 的 C 对象都由 make 并行调度。
只想生成构建文件、不立刻编译时用 `--prepare-only`，它会打印对应的 `make` 命令。
清理用 `make clean` 或 `python3 ../linuxcpp/python/build.py . --clean`。

## module.toml

```toml
[module]
name = "hello_cpp"                 # 模块名，也是 .ko 文件名
description = "Minimal C++ kernel module"
license = "GPL"

[device]
name = "hello_cpp"                 # /dev/ 下的设备名
mode = "0666"                      # 设备节点权限

[bindings]
# 需要完整定义（访问字段）的内核类型；会追加到核心默认集合，依赖递归展开
roots = ["file", "file_operations", "kiocb", "iov_iter", "miscdevice"]
# 内核导出函数，自动生成 extern "C" 声明（同样追加到核心默认集合）
extern = ["misc_register", "misc_deregister", "compat_ptr_ioctl"]
# static inline 函数，自动生成 C thunk
thunk = ["copy_to_iter", "copy_from_iter", "copy_from_user", "copy_to_user"]
# 无参对象宏，自动导出成 linuxcpp::NAME
# macro = ["MAY_READ"]
# 可选：解析函数声明和 static inline 用的内核头，默认一组常用头
# headers = ["linux/fs.h", "linux/sched.h"]
```

`roots`/`extern` 是增量，核心库 `linuxcpp.cpp`/`device.cpp` 需要的类型和 misc 注册函数始终会带上，用户写的名字只做追加。`roots` 也不是完整类型列表：生成器沿 BTF 递归求依赖闭包，字段需要的类型生成完整定义，指针参数需要的类型生成前向声明。只写 `file`，`inode`、`dentry`、`path`、`file_operations` 等也会自动出现。想用 `task_struct`、`tty_struct` 之类，把名字直接加进 `roots` 即可；头文件只在解析 `extern` 导出函数、`thunk` 的 static inline 定义和 `macro` 时才会用到。

常用 errno（`EPERM`、`EINVAL`、`ENOTTY` 等）默认就会导出成 `linuxcpp::EINVAL`，不用手写。

### 怎么判断一个内核 API 属于哪类

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

### 宏

对象宏（`#define MAY_READ 0x4`）没有参数，预处理器展开后就是一个表达式，可以自动导出成 `inline constexpr auto`；用 `[bindings] macro = [...]` 指定，常用 errno 默认导出。

函数宏（`_IOW`、`copy_to_user`、`container_of`、`pr_info`）在预处理阶段做 token 替换，依赖 `typeof`、语句表达式、`#`/`##`、参数多次求值，AST 里没有它们的函数语义，不能可靠自动翻译。处理方式：

- 能包成普通函数的，写进 `thunk`，生成器生成 C 包装（`copy_to_user` 就是）；
- 纯计算/常量组合的，用 `constexpr` 重写（`ioctl_misc` 示例里的 `_IOC`）；
- 依赖内核内部符号或特殊语句的，手写 C thunk，放进模块目录的 `.c` 文件（构建器会编译并链接）。

## driver.cpp

默认体验和写 C 模块一样：自己定义回调、自己填 `file_operations`、自己调 `misc_register`，不需要继承任何类。

```cpp
#include "linuxcpp.hpp"

static ssize_t my_read(linuxcpp::kiocb *iocb, linuxcpp::iov_iter *to)
{
    // read_iter 的位置是 ki_pos，内核返回后会同步回 file->f_pos
    if (iocb->ki_pos > 0)
        return 0;
    static constexpr char message[] = "hello\n";
    linuxcpp::ssize_t n = static_cast<linuxcpp::ssize_t>(
        linuxcpp::lc_copy_to_iter(message, sizeof(message) - 1, to));
    iocb->ki_pos += n;
    return n;
}

// 和 C 里完全一样，用 C++20 的指定初始化填字段
static const linuxcpp::file_operations my_fops = {
    .owner = linuxcpp::this_module(),
    .read_iter = my_read,
};

static linuxcpp::miscdevice my_misc = {
    .minor = linuxcpp::MISC_DYNAMIC_MINOR,
    .name = LCPP_DEVICE_NAME,  // 来自 module.toml 的 [device]
    .fops = &my_fops,
    .mode = LCPP_DEVICE_MODE,
};

static int my_init(void)
{
    return linuxcpp::misc_register(&my_misc);
}

static void my_exit(void)
{
    linuxcpp::misc_deregister(&my_misc);
}

LCPP_MODULE_RAW(my_init, my_exit)
```

- `linuxcpp::this_module()` 等价于 C 的 `THIS_MODULE`。
- `LCPP_DEVICE_NAME` / `LCPP_DEVICE_MODE` 由 `module.toml` 的 `[device]` 生成。
- `LCPP_MODULE_RAW` 只生成 `module_init`/`module_exit`，里面注册 misc、chrdev、platform driver、kthread 都行；一个 init 里注册多个设备也可以。
- C 入口文件永远只有 `module_init`/`module_exit`。

### 可选：Device 对象风格

库只提供 `linuxcpp::Device` 基类和 `linuxcpp::misc_device`；实例放全局、静态缓冲还是堆上，
由用户自己的 `.cpp` 决定，库不替模块保存任何状态。

```cpp
#include "device.hpp"

class MyDevice : public linuxcpp::Device {
public:
    linuxcpp::ssize_t read(linuxcpp::kiocb *iocb, linuxcpp::iov_iter *to) override
    {
        return linuxcpp::lc_copy_to_iter("hello\n", 6, to);
    }
};

static MyDevice my_device;
static linuxcpp::misc_device my_misc(&my_device, LCPP_DEVICE_NAME, LCPP_DEVICE_MODE);

static int my_init(void)
{
    return my_misc.start();
}

static void my_exit(void)
{
    my_misc.stop();
}

LCPP_MODULE_RAW(my_init, my_exit)
```

`Device` 提供 `open/release/read/write/ioctl` 虚方法，默认 `open`/`release` 返回 0，其余返回 `-EINVAL`/`-ENOTTY`。
`misc_device` 自己持有 `file_operations` 和 `miscdevice`，回调通过 `file->f_op` 反查实例、
`file->private_data` 保存 `Device*`，所以每个实例独立，可以同时注册多个设备。`name` 必须指向静态生命周期字符串。

## 核心库

标准库设施固定放在 `linuxcpp::std` 下，头文件在 `linuxcpp/include/std/`；绑定和核心库统一在 `linuxcpp` 命名空间，宏前缀是 `LCPP_`，C 符号前缀是 `lcpp_`。

| 设施 | 说明 |
|---|---|
| `std::unique_ptr<T>` / `std::unique_ptr<T[]>` | RAII 管理内核堆，数组版本析构时 `delete[]` |
| `std::vector<T>` | 自写动态数组，支持 move、begin/end、data/front/back、pop_back，没有 STL |
| `std::array<T, N>` | 固定大小数组，begin/end 可直接用于范围 for |
| `std::span<T>` | 指针 + 长度视图，begin/end、subspan 越界会夹到合法范围 |
| `std::string_view` | 非拥有字符串视图（`starts_with`/`ends_with`/`find`/`substr`） |
| `std::fixed_string<N>` | 对象内固定容量字符串，`assign` 返回是否被截断 |
| `linuxcpp::wrappers::intrusive_list<T, Offset>` | 包装内核 `list_head` 的侵入式链表 |
| `LCPP_LIST(T, member)` | 用 `offsetof` 构造上面的链表类型；默认 `roots` 已包含 `list_head` |
| `linuxcpp::wrappers::hlist<T, Offset>` | 包装 `hlist_node`/`hlist_head`，用 `LCPP_HLIST` 构造 |
| `linuxcpp::wrappers::timestamp` | 包装 `timespec64`，支持纳秒换算、比较、加减 |
| `linuxcpp::wrappers::kvec` / `iovec` | 包装内核 `kvec`/`iovec` |
| `linuxcpp::wrappers::completion` | 包装 `completion`，按文件头注释配置 roots/extern/thunk |
| `linuxcpp::wrappers::spinlock` / `spin_guard` | 包装 `spinlock_t`，按文件头注释配置 roots/thunk |
| `linuxcpp::wrappers::atomic` | 包装 `atomic_t`，thunk 由核心库手写提供 |
| `std::mutex` / `std::lock_guard` | 内核 mutex 的 RAII 封装；handle 内嵌在对象里，不分配，`ok()` 恒为 true |
| `std::scope_guard` / `std::make_scope_guard` | 作用域退出时执行清理 |
| `std::is_error` / `std::ptr_error` / `std::error_ptr` | 错误指针判断和转换（IS_ERR/PTR_ERR/ERR_PTR） |
| `linuxcpp::EINVAL` 等 | 内核错误码，从 errno 宏自动导出 |
| `linuxcpp::printk` | 变参 printk 包装，内部走 `vprintk`，用法和内核 printk 一致 |
| `operator new/delete` | 已重载到 `kmalloc`/`kfree`，数组版本同样可用 |
| `misc_device` | 每个实例内嵌自己的 fops/miscdevice，`start()`/`stop()` 注册和注销 |
| `LCPP_MODULE_RAW(I, E)` | 只生成 init/exit，自己决定注册什么 |

这些包装类按需 include，不放进 `linuxcpp.hpp`。需要额外内核类型的配置示例：

```toml
[bindings]
roots = ["completion", "spinlock_t", "atomic_t", "hlist_node", "hlist_head",
         "timespec64", "kvec", "iovec"]
extern = ["wait_for_completion", "complete", "complete_all"]
thunk = ["init_completion", "spin_lock", "spin_unlock"]
headers = ["linux/completion.h", "linux/spinlock.h", "linux/atomic.h",
           "linux/list.h", "linux/time64.h"]
```

`atomic` 不需要配置 `thunk`；`spin_lock_init` 也由 `linuxcpp_thunks.c` 手写提供。

C++ 层不能使用异常、RTTI、STL。构建器已经加上 `-fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit`。
生成的 C 入口会在 `module_init` 前调用 `.init_array` 里的全局构造函数，在 `module_exit` 后逆序调用
`.fini_array` 里的析构函数；模块 init 失败时也会逆序运行 `.fini_array`，已经构造成功的全局对象会正常析构。

## 构建流程

`build.py` 做这些事：

1. 读 `module.toml`
2. 调 `python/gen_bindings.py`（实现在 `python/linuxcppgen/`）：BTF → 结构体镜像、`layout_check.c`、`thunks_gen.c`
3. 生成 `entry_gen.c`（只有 module_init/exit）和 `generated/config.hpp`，复制 `linuxcpp_thunks.c`
4. 让 kbuild 编译一个 C 对象，抓出内核真实的 C 编译器 flags，写入 `generated/cxxflags.mk`
5. 生成 `Makefile`，之后由 make 增量构建：C++ 对象用 `-MMD -MP` 跟踪头文件，kbuild 负责 C 对象和链接

`Makefile` 只在 `module.toml`、生成器或核心库源码变化时重新运行 `--prepare-only`；改 `driver.cpp`
只重编对应对象。`make -j` 的并行度由 make 自己控制，`build.py` 默认最多传 `-j6`，也可以手动指定。

## 内核升级

- 每次构建检查 `generated/vmlinux.h` 的缓存标识（内核 release + BTF 大小/时间），换内核后重新导出。
- 结构体、typedef、枚举、字段偏移来自 BTF；函数声明来自 libclang AST；`layout_check.c` 编译时用 `static_assert` 对比真实内核头。bpftool 生成 `vmlinux.h` 时会漏掉部分 `__packed`/`aligned`，生成器会按 BTF 的 size/bit offset 自动重建这些类型，不依赖 clang 算出的错误布局。
- 常量宏（errno、`MAX_ERRNO`、`MISC_DYNAMIC_MINOR`、`_IOC_*`）由预处理器展开后导出，不写死数值。
- C thunk 直接 include 内核头，`kmalloc`、`mutex_init` 这类宏随内核头变化。
- 仍写死的是内核 API 的名字（`misc_register`、`file_operations.owner` 等）；改名会编译失败，不会静默用错偏移。

## 限制

- **函数宏**：对象宏可以自动导出，但 `kmalloc`、`WARN_ON`、`DEFINE_MUTEX` 这类函数宏是预处理 token 替换，需要手写 thunk 或 C++ 等价物。
- **全局对象**：生成的 C 入口会调用 `.init_array`/`.fini_array`，全局构造/析构可以正常使用；
  析构在 `lcpp_module_exit` 之后逆序执行，init 失败时也会逆序析构。自定义 C 入口需要自己调用
  `lcpp_run_init_array()` / `lcpp_run_fini_array()`，否则全局对象不会构造/析构。
- **内联汇编**：`asm volatile`/`asm goto` 可以保留在 C thunk 里，但不要指望自动翻译。
- **未导出符号**：C++ 层不能直接调用没有 `EXPORT_SYMBOL` 的函数，必须走 C thunk。
- **全量翻译不现实**：内核有几万个 static inline，按需绑定才是可维护的做法。
- **模块 BTF**：pahole 处理 C++ 模板的 DWARF 会报错，构建器关闭了模块 BTF 生成（只影响 BPF 跟踪）。
- **对齐**：`operator new` 只保证 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`（通常 16 字节）；
  `alignas` 更大的类型请自己分配内存再 placement new，`std::vector` 对这类元素会直接 static_assert 失败。
- **设备所有权**：`misc_device` 不接管 `Device*`，Device 对象由用户自己管理；`name` 必须指向静态生命周期字符串。
  每个 `misc_device` 实例独立注册一个 misc 节点，库不保存模块级全局状态。
- **分配失败**：`operator new` 失败返回 `nullptr`，不抛异常；`std::mutex` 的 handle 内嵌在对象里，
  没有创建失败路径，`ok()` 恒为 true 仅为兼容旧调用方。`operator new`、`vector` 扩容都走
  `GFP_KERNEL`，只能在可睡眠上下文使用。

## 已知坑（构建器已处理）

- C++ 对象的 `__patchable_function_entries` 带 `SHF_GNU_RETAIN`，链接器不合并，`insmod` 会报 EEXIST。构建器会去掉 `-fpatchable-function-entry`。
- 内核的 `module_init` 宏要求 alias 目标在本编译单元有定义，不能直接 alias 到 C++ 的 `extern` 符号。生成的 `entry_gen.c` 会加一层本地包装函数。
- C++ 编译器与内核 C 编译器不是同一套（例如内核 GCC、C++ 用 clang++）时，
  内核的新 codegen flags 可能不被识别；推荐让 C++ 编译器跟随内核工具链。
- `copy_from_user` 的 `__user` 注解在 clang 的 spelling 里会消失，ABI 不受影响。

## 示例

每个目录都能独立构建：

```bash
cd examples/hello_misc
python3 ../../linuxcpp/python/build.py .
sudo insmod hello_misc.ko
cat /dev/hello_misc
sudo rmmod hello_misc
```

| 目录 | 内容 |
|---|---|
| `examples/hello_misc` | 最小 misc 设备（C 风格 fops） |
| `examples/ioctl_misc` | ioctl + `copy_from_user`/`copy_to_user` + `mutex` + 对象宏导出 |
| `examples/two_devices` | 一个模块注册两个 misc 设备 |
| `examples/kthread_demo` | 内核线程（非设备模块） |
| `examples/etl_kv` | ETL 固定容量容器的内存键值存储（`echo` 写命令、`cat` 读结果） |
| `raw_demo/` | 最小 raw 模块 |

### ETL 集成

`examples/etl_kv` 演示第三方无 STL 库的接法：

- ETL 头在 `linuxcpp/third_party/etl/include`；
- `linuxcpp/python/gen_libc_shim.py` 生成 `stdint.h`、`limits.h`、`new` 等 freestanding shim；
- `module.toml` 的 `[build]` 用 `cxx_includes` 加头路径、`cxx_flags` 加
  `-DETL_NO_STL -DETL_NO_STD_MUTEX`；
- 动态对象用 `linuxcpp::std::unique_ptr` 在 init 里创建、exit 里销毁。

```bash
echo "set name linuxcpp" > /dev/etl_kv
echo "get name" > /dev/etl_kv && cat /dev/etl_kv
```

## License

除 `linuxcpp/third_party/` 下的依赖保留其自身许可证（ETL 为 MIT）外，本项目以
GPL-3.0-or-later 发布，完整文本见 `LICENSE`。内核模块入口仍使用
`MODULE_LICENSE("GPL")` 以访问内核的 GPL 符号；实际分发时请自行确认目标内核的
许可证兼容性。
