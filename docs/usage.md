# 写模块

## driver.cpp

默认体验和写 C 模块一样：自己定义回调、自己填 `file_operations`、自己调 `misc_register`，不需要继承任何类。

```cpp
#include "linuxcpp.hpp"

static linuxcpp::ssize_t my_read(linuxcpp::kiocb *iocb, linuxcpp::iov_iter *to)
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

## 可选：Device 对象风格

库只提供 `linuxcpp::Device` 基类和 `linuxcpp::misc_device`；实例放全局、静态缓冲还是堆上，由用户自己的 `.cpp` 决定，库不替模块保存任何状态。

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

`Device` 提供 `open/release/read/write/ioctl` 虚方法，默认 `open`/`release` 返回 0，其余返回 `-EINVAL`/`-ENOTTY`。`misc_device` 自己持有 `file_operations` 和 `miscdevice`，回调通过 `file->f_op` 反查实例、`file->private_data` 保存 `Device*`，所以每个实例独立，可以同时注册多个设备。`name` 必须指向静态生命周期字符串。

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
| `operator new/delete` | 已重载到 `kmalloc`/`kfree`，普通、数组、aligned、nothrow 版本都可用 |
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

## 内存和上下文

`operator new/delete` 是核心库的一部分，不依赖 libc++；普通、数组、aligned、nothrow 版本都始终可用。分配最终走 `kmalloc(..., GFP_KERNEL)`，只能在可睡眠上下文调用。每次分配前会调用 `might_sleep()`，在原子上下文里误用会让内核打印调用栈，而不是等到真正睡眠时才报错。

`operator new` 失败返回 `nullptr`，不抛异常；`std::vector` 扩容也走同一套分配器。`std::mutex` 的 handle 内嵌在对象里，没有创建失败路径，`ok()` 恒为 true 仅为兼容旧调用方。

## 构造和析构

默认构建不能使用异常、RTTI、STL。构建器已经加上 `-fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit`；使用 libc++ 后可以用标准库子集，但异常和 RTTI 仍然关闭。

生成的 C 入口会在 `module_init` 前调用 `.init_array` 里的全局构造函数，在 `module_exit` 后逆序调用 `.fini_array` 里的析构函数；模块 init 失败时也会逆序运行 `.fini_array`，已经构造成功的全局对象会正常析构。

## ETL 集成

ETL 是推荐的内核容器库：固定容量、无动态分配、无异常/RTTI，MIT 许可证和本项目的
GPL-2.0-only 兼容。需要可预测内存占用的模块优先用 ETL，而不是 libc++ 的动态容器。

`examples/etl_kv` 演示第三方无 STL 库的接法：

- ETL 不随仓库分发；在仓库根目录 clone 20.49.0：`git clone --depth 1 --branch 20.49.0 https://github.com/ETLCPP/etl.git third_party/etl`
- ETL 头在 `third_party/etl/include`，`examples/etl_kv` 用 `../../third_party/etl/include` 引用
- `libc_port/include` 提供 `<new>`、`<cstddef>`、`<stdint.h>` 等 freestanding 头，模块默认 include `libc.mk`，不再需要单独的 ETL shim
- `module.toml` 的 `[build]` 用 `cxx_includes` 加 ETL 头路径、`cxx_flags` 加 `-DETL_NO_STL -DETL_NO_STD_MUTEX`
- 动态对象用 `linuxcpp::std::unique_ptr` 在 init 里创建、exit 里销毁

```bash
echo "set name linuxcpp" > /dev/etl_kv
echo "get name" > /dev/etl_kv && cat /dev/etl_kv
```
