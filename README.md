# linuxcpp：用 C++ 写 Linux 内核模块

[English](README.en.md)

linuxcpp 是一套工具链：写一个 `module.toml` 和一个 C++ 文件，就能编译出可加载的 Linux 内核模块。类型绑定、函数声明、C 入口、Kbuild、布局校验全部自动生成；构建方式保持 kbuild 风格，模块 Makefile 只做声明。

```bash
python3 linuxcpp/python/build.py --init ../my_module
make -C ../my_module -j6
sudo insmod ../my_module/my_module.ko
cat /dev/my_module
sudo rmmod my_module
```

## 为什么不能直接 include 内核头

C++ 编译器解析内核头会失败，原因是两类：

- 关键字冲突：`struct class`、字段名 `private`、宏参数名 `not`（C++ 的替代运算符）
- C 专用语法：`typeof`、复合字面量、designated initializers、`_Generic`、`__builtin_types_compatible_p`、语句表达式

所以 linuxcpp 把工作拆成三层：

```
BTF (bpftool)              → 类型布局 → C/C++ 结构体镜像 + static_assert 校验
内核头 (libclang AST)       → 导出函数声明、static inline 的 C thunk
核心库 (linuxcpp_thunks.c)  → 宏和初始化函数的手写 thunk
```

C++ 代码只 include `linuxcpp.hpp`（需要 `Device` 时再 include `device.hpp`）和生成的 `bindings.hpp`，完全不碰内核头。

## 特性

- kbuild 风格：`MODULE_NAME`、`obj-m`、`$(MODULE_NAME)-y`、`ccflags-y`、`cxxflags-y`
- BTF 自动生成结构体镜像和前向声明，`layout_check.c` 在编译期校验布局
- 自动处理 `.init_array`/`.fini_array`，全局构造/析构可用
- 核心库提供 `linuxcpp::std` 下的容器、RAII、错误码和设备封装
- 可选内核版 libc++，作为独立的 `libcxx_runtime.ko` 加载；libc++ 源码由脚本自行下载，不随仓库分发
- 推荐用 [ETL](https://github.com/ETLCPP/etl) 作为内核里的固定容量容器库（MIT，兼容 GPL-2.0-only）；CTRE、RapidJSON 等无 STL 库也需自行下载，见 `examples/README.md`

## 目录结构

```
test_rust/
├── Makefile                    仓库入口（runtime/examples/test/clean）
├── linuxcpp/
│   ├── include/                公开 C++ 头（linuxcpp.hpp/device.hpp/std/wrappers/ctre_kernel.hpp）
│   ├── src/                    C/C++ 实现（linuxcpp.cpp/device.cpp/linuxcpp_thunks.c）
│   ├── libc_port/              内核 C 库子集（静态头 + 按目标内核生成的类型/errno）
│   ├── libcxx_port/            libc++ 内核配置、下载脚本和去浮点运行库源码
│   ├── runtime/                libc++ 共享运行库模块 libcxx_runtime.ko
│   ├── libc.mk                 使用内核 C 库子集的编译参数片段
│   ├── libcxx.mk               使用共享 libc++ 的编译参数片段
│   ├── Makefile                模块构建 driver（make -C linuxcpp M=模块目录）
│   └── python/                 构建和绑定生成脚本
├── third_party/                自行下载的 libc++/ETL/CTRE/RapidJSON 等第三方库（不入库）
├── template/                   最小模块模板（misc 设备）
├── examples/                   可编译示例
├── raw_demo/                   raw 类型示例（不注册设备）
├── docs/                       详细文档
├── README.md                   中文说明
└── README.en.md                English README
```

## 依赖

- Linux 内核头或源码树（`/lib/modules/$(uname -r)/build`）
- Python 3.11+（`tomllib`）
- libclang Python 绑定：`apt install python3-clang-22`
- `bpftool`（真实二进制；如果系统 wrapper 找不到自编内核，脚本会自动扫 `/usr/lib/linux-tools/*/bpftool`）
- C++ 编译器：默认跟随 kbuild 的 C 编译器（GCC → `g++`，clang → `clang++`），也可以在 `module.toml` 的 `[build] cxx` 里指定
- 内核开启 `CONFIG_MODULES`，最好有 `CONFIG_DEBUG_INFO_BTF`
- 使用 libc++ 时（可选）：先执行 `python3 linuxcpp/libcxx_port/update_libcxx.py`，把 libc++ 20.1.8 下载到 `third_party/libcxx/`

## 测试状态

目前只在下面这个内核上实际构建、加载并运行过模块：

- `6.18.33.1-microsoft-standard-WSL2`（x86_64，WSL2）

其他内核版本和架构（ARM64、其他发行版内核等）**尚未验证**。绑定生成、
`libc_port` 的 errno/类型头和 libc++ 运行库都按目标内核和编译器生成，换内核后
需要重新构建并自行验证。

## 快速开始

在仓库根目录创建一个新模块：

```bash
python3 linuxcpp/python/build.py --init ../my_module
make -C ../my_module -j6
sudo insmod ../my_module/my_module.ko
cat /dev/my_module
sudo rmmod my_module
```

`--init` 会生成：

- `module.toml`：模块名、设备名、可选的绑定配置
- `Makefile`：kbuild 风格声明，直接 `make` 时转交给 `linuxcpp/Makefile`
- `driver.cpp`：最小 misc 设备示例，和 `template/driver.cpp` 相同

也可以直接复制模板：

```bash
cp -r template mymodule
cd mymodule
python3 ../linuxcpp/python/build.py .
make -j6
```

第一次构建会生成 `Kbuild`、`generated/`、`generated/cxxflags.mk` 和入口 `Makefile`。之后在模块目录直接 `make -j6` 即可；C++ 对象用 `-MMD -MP` 跟踪头文件依赖，C 对象和链接交给 kbuild。只想生成构建文件、不立刻编译时用 `--prepare-only`。

## 仓库级命令

```bash
make runtime    # 构建 linuxcpp/runtime/libcxx_runtime.ko
make examples   # 先构建运行库，再并行构建 examples/ 下的模块
make test       # 运行 pytest
make check      # test + examples
make clean      # 清理运行库和示例
```

默认并行度是 6，可以覆盖：`make runtime JOBS=4`。`examples/std_demo` 使用 libc++，
所以 `make examples` 会先构建 `libcxx_runtime.ko`。构建前需要先下载 libc++：

```bash
python3 linuxcpp/libcxx_port/update_libcxx.py
```

需要代理时设置 `HTTPS_PROXY=http://127.0.0.1:7897`。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/build-system.md](docs/build-system.md) | module.toml 的 `[build]`、Makefile/kbuild、构建流程、内核升级 |
| [docs/bindings.md](docs/bindings.md) | `roots`/`extern`/`thunk`/`macro`/`headers` 的分类和诊断 |
| [docs/usage.md](docs/usage.md) | `driver.cpp` 写法、`Device` 对象、核心库、ETL |
| [docs/libc.md](docs/libc.md) | 内核 C 库子集：支持范围、生成的头、malloc/qsort/printf、和内核头的关系 |
| [docs/libcxx.md](docs/libcxx.md) | 共享 libc++ 运行库、限制、C 头 shim、CTRE |
| [docs/troubleshooting.md](docs/troubleshooting.md) | 常见链接/加载错误、调试、编辑器集成、已知限制 |

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
| `examples/libc_demo` | 不用 libc++，直接使用 `malloc/qsort/strtol/snprintf/printf/time` |
| `examples/std_demo` | libc++ 标准库覆盖面：容器、optional/variant/any、chrono、charconv 等 |
| `examples/sysinfo_json` | 用 RapidJSON 返回格式化系统统计 JSON（内存、CPU、负载、任务数、uptime） |
| `examples/json_format` | 用户传入 JSON 文件 fd，内核用 RapidJSON+FPU 解析并原地格式化 |
| `raw_demo/` | 最小 raw 模块 |

## License

本项目以 GPL-2.0-only 发布，完整文本见 `LICENSE`，和 Linux 内核保持一致。

libc++ 不随仓库分发，由 `linuxcpp/libcxx_port/update_libcxx.py` 自行下载，仍按 Apache-2.0 WITH LLVM-exception 授权；自行下载的 ETL、RapidJSON 为 MIT，CTRE 为 Apache-2.0。内核模块入口使用 `MODULE_LICENSE("GPL")` 以访问内核的 GPL 符号。

用本项目写的模块，如果只分发自己的源码（连同构建脚本），通常没有问题；但把链接了 Apache-2.0 libc++ 的 `.ko` 作为整体分发时，Apache-2.0 与 GPL-2.0-only 的组合存在兼容性问题。实际分发前请自行确认目标内核和所有依赖的许可证。
