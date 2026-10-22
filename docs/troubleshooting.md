# 排错和限制

## 常见链接错误

### `modpost: "xxx" undefined!`

说明 C++ 代码引用了某个符号，但当前 `.ko` 里没有定义，也没有从其他模块导入。

- 如果 `xxx` 是内核导出函数：检查它是否在 `[bindings] extern` 里；分类错误时看生成器的警告
- 如果 `xxx` 是 `static inline`：把它放到 `[bindings] thunk`，不要放 `extern`
- 如果是函数宏：在模块目录的 `.c` 文件里手写包装，构建器会自动编译
- 如果是 `libcxx_runtime` 提供的 C++ 符号：确认模块 Makefile 里有
  `KBUILD_EXTRA_SYMBOLS := $(LINUXCPP)/runtime/Module.symvers`，并且运行库已经构建

### `insmod: unknown symbol in module`

通常是加载顺序问题。使用共享 libc++ 时先加载运行库：

```bash
sudo insmod linuxcpp/runtime/libcxx_runtime.ko
sudo insmod my_module.ko
```

卸载时反过来：

```bash
sudo rmmod my_module
sudo rmmod libcxx_runtime
```

`lsmod` 里运行库的引用计数会显示还有哪些模块依赖它。

### `insmod: EEXIST` / 重复的 section

C++ 对象的 `__patchable_function_entries` 带 `SHF_GNU_RETAIN`，链接器不会合并。构建器已经去掉 `-fpatchable-function-entry`；如果自己改 Makefile，不要再加回来。

### `bpftool` / BTF 相关失败

- 内核需要 `CONFIG_DEBUG_INFO_BTF`，或者至少 `/sys/kernel/btf/vmlinux`
- 系统自带的 `bpftool` wrapper 找不到自编内核时，脚本会自动扫 `/usr/lib/linux-tools/*/bpftool`
- 换内核后如果 `generated/vmlinux.h` 缓存没更新，执行 `python3 linuxcpp/python/build.py . --clean` 再构建

## 运行时问题

### `BUG: sleeping function called from invalid context` / `might_sleep` 警告

`operator new`、`std::vector` 扩容都走 `kmalloc(..., GFP_KERNEL)`，只能在可睡眠上下文调用。构建器在每次分配前调用 `might_sleep()`，在自旋锁、中断、RCU 读临界区里分配会立刻打印调用栈。

解决方式：在进入原子上下文前完成分配，或者用 `kmalloc(..., GFP_ATOMIC)` 自己分配再 placement new：`operator new(size_t, void*)` 不调用分配器。

### 模块加载后没有 `/dev/xxx`

检查 `misc_register` 的返回值。`init` 返回非 0 时模块加载会失败，`dmesg` 里有原因。设备名和权限来自 `module.toml` 的 `[device]`；修改后需要重新构建。

### 全局对象没有构造/析构

默认入口由构建器生成，会在 `module_init` 前跑 `.init_array`、`module_exit` 后逆序跑 `.fini_array`。如果用了自定义 C 入口（`[module] entry`），需要自己调用 `lcpp_run_init_array()` / `lcpp_run_fini_array()`。

## 编辑器 / clangd

项目没有生成 `compile_commands.json`；用 `bear` 抓一次构建即可：

```bash
bear -- make -C my_module -j6
```

之后 clangd 能读到 `compile_commands.json`，补全和跳转基于内核构建时真实的 include 路径。重新构建或换内核后需要重跑 `bear`。

## 已知限制

- **函数宏**：对象宏可以自动导出，但 `kmalloc`、`WARN_ON`、`DEFINE_MUTEX` 这类函数宏是预处理 token 替换，需要手写 thunk 或 C++ 等价物。
- **全局对象**：可以正常构造/析构，但析构发生在模块卸载路径上，不能假设还能睡眠或访问已经注销的设备。
- **内联汇编**：`asm volatile`/`asm goto` 可以保留在 C thunk 里，但不要指望自动翻译。
- **未导出符号**：C++ 层不能直接调用没有 `EXPORT_SYMBOL` 的函数，必须走 C thunk，或者由另一个模块导出并用 `KBUILD_EXTRA_SYMBOLS` 链接。
- **全量翻译不现实**：内核有几万个 static inline，按需绑定才是可维护的做法。
- **模块 BTF**：pahole 处理 C++ 模板的 DWARF 会报错，构建器关闭了模块 BTF 生成（只影响 BPF 跟踪）。
- **对齐**：`operator new` 现在支持 aligned 版本，但 `std::vector` 对超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 的元素仍会 static_assert；这种类型请自己分配内存再 placement new。
- **设备所有权**：`misc_device<D>` 由用户继承并持有，构造时注册、析构时注销；`name` 必须指向静态生命周期字符串。
- **分配失败**：`operator new` 失败返回 `nullptr`，不抛异常；使用前要检查。`std::mutex` 的 handle 内嵌在对象里，没有创建失败路径，`ok()` 恒为 true 仅为兼容旧调用方。

## 许可证

本项目以 GPL-2.0-only 发布，完整文本见仓库根 `LICENSE`。自行下载的第三方库保留各自许可证：libc++ 为 Apache-2.0 WITH LLVM-exception，ETL/RapidJSON 为 MIT，CTRE 为 Apache-2.0。内核模块入口使用 `MODULE_LICENSE("GPL")` 以访问内核的 GPL 符号。分发链接了 libc++ 的 `.ko` 时，Apache-2.0 与 GPL-2.0-only 的组合存在许可证兼容性问题，只分发自己模块的源码通常没有这个问题。
