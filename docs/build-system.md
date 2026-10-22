# 构建系统

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
# 类型和函数的接入配置，详见 bindings.md
roots = ["file", "file_operations", "kiocb", "iov_iter", "miscdevice"]
extern = ["misc_register", "misc_deregister", "compat_ptr_ioctl"]
thunk = ["copy_to_iter", "copy_from_iter", "copy_from_user", "copy_to_user"]

[build]
# 额外 C++ 头文件目录，相对模块目录
# cxx_includes = ["../../third_party/etl/include"]
# 额外 C++ flags
# cxx_flags = ["-DETL_NO_STL"]
# 指定 C++ 编译器；留空跟随 kbuild 的 C 编译器
# cxx = "clang++"
```

`roots`/`extern`/`thunk` 是增量，核心库 `linuxcpp.cpp`/`device.cpp` 需要的类型和 misc 注册函数始终会带上，用户写的名字只做追加。`roots` 也不是完整类型列表：生成器沿 BTF 递归求依赖闭包，字段需要的类型生成完整定义，指针参数需要的类型生成前向声明。只写 `file`，`inode`、`dentry`、`path`、`file_operations` 等也会自动出现。想用 `task_struct`、`tty_struct` 之类，把名字直接加进 `roots` 即可；头文件只在解析 `extern` 导出函数、`thunk` 的 static inline 定义和 `macro` 时才会用到。

常用 errno（`EPERM`、`EINVAL`、`ENOTTY` 等）默认就会导出成 `linuxcpp::EINVAL`，不用手写。

## 模块 Makefile

自动生成的入口 Makefile 只做声明；直接 `make` 时转交给 `linuxcpp/Makefile` 这个 driver：

```bash
make -C ../linuxcpp M=$(pwd)
```

driver 设置 `LINUXCPP_BUILD=1` 后再 include 模块 Makefile，模块文件据此跳过自己的 `all`/`clean`，目标和规则的所有权始终在 driver 这边，不会出现两个 `clean` 互相覆盖。之后在模块目录直接 `make -j6` 即可。C++ 对象用 `-MMD -MP` 跟踪头文件依赖，C++ 对象和 kbuild 的 C 对象都由 make 并行调度。只想生成构建文件、不立刻编译时用 `--prepare-only`，它会打印对应的 `make` 命令。清理用 `make clean` 或 `python3 ../linuxcpp/python/build.py . --clean`。

手写 Makefile 用同样的约定：直接 make 的分支里写自己的 `all`/`clean`，被 driver include 的分支里只放声明。`build.py` 不会覆盖没有自动生成标记的 `Makefile`：

```make
KDIR ?= /lib/modules/$(shell uname -r)/build
LINUXCPP ?= /path/to/linuxcpp

ifeq ($(LINUXCPP_BUILD),)
all:
	$(MAKE) -C $(LINUXCPP) M=$(CURDIR) KDIR="$(KDIR)"

clean:
	$(MAKE) -C $(LINUXCPP) M=$(CURDIR) KDIR="$(KDIR)" clean
	rm -f my_extra_file
else
MODULE_NAME := mymodule
obj-m := $(MODULE_NAME).o
$(MODULE_NAME)-y := driver.o extra.o
ccflags-y += -DXXX
cxxflags-y += -DYYY
endif
```

`all`/`clean` 在 `ifeq ($(LINUXCPP_BUILD),)` 分支里，driver include 时看不到它们，所以可以在调用完公共 clean 后追加自己的清理命令。公共规则会把 `lcpp_ctors_start.o` 到 `lcpp_ctors_end.o` 的核心对象按正确顺序插进 `$(MODULE_NAME)-y`，你追加的对象会参与最终链接。

`obj-m` 和 kbuild/Rust 一样始终是最终模块的聚合对象（`.o`），不是源文件；C++ 源文件编译出的 `.o` 放在 `$(MODULE_NAME)-y` 里。Rust 的单文件模块写 `obj-m := foo.o`，多文件模块写 `foo-y := a.o b.o`，和这里的结构一致。

## 构建流程

`build.py` 做这些事：

1. 读 `module.toml`
2. 调 `python/gen_bindings.py`（实现在 `python/linuxcppgen/`）：BTF → 结构体镜像、`layout_check.c`、`thunks_gen.c`
3. 生成 `entry_gen.c`（只有 module_init/exit）和 `generated/config.hpp`，复制 `linuxcpp_thunks.c`
4. 让 kbuild 编译一个 C 对象，抓出内核真实的 C 编译器 flags，写入 `generated/cxxflags.mk`
5. 生成模块目录的 kbuild 风格声明 `Makefile`；直接 make 时它转交给 `linuxcpp/Makefile` driver（`M=` 指定模块目录）。driver 设置 `LINUXCPP_BUILD` 后 include 模块文件，只读取声明，之后由 make 增量构建

公共规则在 `linuxcpp/Makefile`；入口 Makefile 只在 `module.toml`、生成器或核心库源码变化时重新运行 `--prepare-only`，改 `driver.cpp` 只重编对应对象。`make -j` 的并行度由 make 自己控制，`build.py` 默认最多传 `-j6`，也可以手动指定。

生成的文件都可以删除后重建：

- `generated/bindings.h`、`generated/bindings.hpp`：C/C++ 类型镜像
- `generated/config.hpp`：模块名、设备名、权限
- `layout_check.c`：编译期布局校验
- `thunks_gen.c`：`thunk` 列表生成的 C 包装
- `entry_gen.c`：`module_init`/`module_exit` 入口
- `Kbuild`：kbuild 对象列表，链接前会按最终 `$(MODULE_NAME)-y` 重写
- `generated/cxxflags.mk`：从 kbuild 提取并转换后的 C++ flags

## 顶层 Makefile

仓库根目录的 `Makefile` 只是常用命令的组合，不改变单模块构建方式：

```bash
make runtime    # 构建 linuxcpp/runtime/libcxx_runtime.ko
make examples   # 依次构建 examples/ 下的模块
make test       # pytest
make check      # test + examples
make clean      # 清理运行库和示例
make help       # 打印命令说明
```

示例是串行构建的，避免多个 `make -j6` 同时跑把内存打满；`JOBS` 默认是 6。

## 内核升级

- 每次构建检查 `generated/vmlinux.h` 的缓存标识（内核 release + BTF 大小/时间），换内核后重新导出。
- 结构体、typedef、枚举、字段偏移来自 BTF；函数声明来自 libclang AST；`layout_check.c` 编译时用 `static_assert` 对比真实内核头。bpftool 生成 `vmlinux.h` 时会漏掉部分 `__packed`/`aligned`，生成器会按 BTF 的 size/bit offset 自动重建这些类型，不依赖 clang 算出的错误布局。
- 常量宏（errno、`MAX_ERRNO`、`MISC_DYNAMIC_MINOR`、`_IOC_*`）由预处理器展开后导出，不写死数值。
- C thunk 直接 include 内核头，`kmalloc`、`mutex_init` 这类宏随内核头变化。
- 仍写死的是内核 API 的名字（`misc_register`、`file_operations.owner` 等）；改名会编译失败，不会静默用错偏移。

## 已知坑（构建器已处理）

- C++ 对象的 `__patchable_function_entries` 带 `SHF_GNU_RETAIN`，链接器不合并，`insmod` 会报 EEXIST。构建器会去掉 `-fpatchable-function-entry`。
- 内核的 `module_init` 宏要求 alias 目标在本编译单元有定义，不能直接 alias 到 C++ 的 `extern` 符号。生成的 `entry_gen.c` 会加一层本地包装函数。
- C++ 编译器与内核 C 编译器不是同一套（例如内核 GCC、C++ 用 clang++）时，内核的新 codegen flags 可能不被识别；推荐让 C++ 编译器跟随内核工具链。
- `copy_from_user` 的 `__user` 注解在 clang 的 spelling 里会消失，ABI 不受影响。
