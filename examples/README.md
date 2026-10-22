# 示例和第三方库

`examples/` 下每个目录都是一个独立模块，在目录里 `make -j6` 即可构建。

## libc++ 源码

`std_demo`、`sysinfo_json`、`json_format` 都依赖 libc++，而 libc++ 不随仓库分发。
第一次构建前在仓库根目录执行：

```bash
python3 linuxcpp/libcxx_port/update_libcxx.py
```

脚本把 libc++ 20.1.8 下载到 `third_party/libcxx/`，需要代理时设置
`HTTPS_PROXY=http://127.0.0.1:7897`。

## std_demo

`examples/std_demo` 使用 libc++，需要先构建运行库（顶层 `make examples` 会自动构建）：

```bash
make runtime
make -C examples/std_demo -j6
sudo insmod linuxcpp/runtime/libcxx_runtime.ko
sudo insmod examples/std_demo/std_demo.ko
cat /dev/std_demo
```

它不涉及文件系统或特殊设备逻辑，只验证容器、chrono、charconv 等标准库设施
在内核里能编译、链接和运行，输出见 `docs/libcxx.md`。

## sysinfo_json

`examples/sysinfo_json` 用 RapidJSON 把内核统计信息序列化成 JSON，通过
`/dev/sysinfo_json` 返回。它依赖 libc++ 运行库，并且需要自行下载 RapidJSON：

```bash
git clone --depth 1 --branch v1.1.0 \
    https://github.com/Tencent/rapidjson.git third_party/rapidjson
make runtime
make -C examples/sysinfo_json -j6
sudo insmod linuxcpp/runtime/libcxx_runtime.ko
sudo insmod examples/sysinfo_json/sysinfo_json.ko
cat /dev/sysinfo_json | python3 -m json.tool
```

RapidJSON 只用写入器（`PrettyWriter` + `StringBuffer`），不解析输入；整数用
`Uint64`/`Int64`，负载保留一位小数用 `RawValue` 输出，避免内核里的
`double`。模块每次 `open` 重新采集一份快照，所以 `cat` 看到的是当前值。

## json_format

`examples/json_format` 接收用户空间传来的 JSON 文件 fd，把文件内容按两格缩进
格式化后原地写回。解析用 RapidJSON 的 SAX 接口，文件必须以 `O_RDWR` 打开：

```bash
git clone --depth 1 --branch v1.1.0 \
    https://github.com/Tencent/rapidjson.git third_party/rapidjson
make runtime
make -C examples/json_format -j6
sudo insmod linuxcpp/runtime/libcxx_runtime.ko
sudo insmod examples/json_format/json_format.ko
python3 examples/json_format/test.py
python3 examples/json_format/test.py /path/to/file.json
sudo rmmod json_format
sudo rmmod libcxx_runtime
```

`test.py` 会先格式化一份内嵌 JSON，再拿一份坏 JSON 验证 ioctl 返回 `EINVAL`。
也可以自己用 `fcntl.ioctl(device_fd, 0x4A01, file_fd)` 调用。

这个模块演示了内核里手动使用 FPU：`format_json.cpp` 单独用
`-msse -msse2 -mstackrealign -mpreferred-stack-boundary=4` 编译，解析区间包在
`kernel_fpu_begin()`/`kernel_fpu_end()` 里；RapidJSON 的 Reader 使用固定静态
栈分配器，FPU 区间内不做 `kmalloc(GFP_KERNEL)`，也不调用会睡眠的函数。
`kParseNumbersAsStringsFlag` 让数字走 `RawNumber`，不会被转成 `double`。

限制和错误码：

- 输入最大 1 MiB，格式化输出最大 4 MiB，超过返回 `EFBIG`；
- 嵌套深度超过 128 返回 `EINVAL`；
- 只接受普通文件，fd 必须同时有读写权限，否则 `EINVAL`/`EACCES`；
- 追加模式文件返回 `EPERM`；
- JSON 语法错误返回 `EINVAL`；
- 分配失败返回 `ENOMEM`。

格式化结果比原文短时，尾部补空格保持文件大小不变，不依赖 truncate。
`kernel_fpu_begin()` 只能在进程上下文调用，不能用于中断上下文；这是示例模块
刻意展示的能力，真实驱动应优先避免在内核里解析 JSON。

## ETL

ETL 是推荐的内核容器库：固定容量、无动态分配、无异常/RTTI，MIT 许可证和
GPL-2.0-only 兼容，适合对内存和延迟敏感的模块。

ETL 不随仓库分发。`examples/etl_kv` 需要它时，在仓库根目录执行：

```bash
git clone --depth 1 --branch 20.49.0 \
    https://github.com/ETLCPP/etl.git third_party/etl
```

头文件在 `third_party/etl/include`，模块通过 `module.toml` 的 `cxx_includes`
引用。ETL 源码本身没有做任何修改。

## CTRE

CTRE 同样不随仓库分发。需要时在仓库根目录 clone：

```bash
git clone --depth 1 --branch v3.11.0 \
    https://github.com/hanickadot/compile-time-regular-expressions.git \
    third_party/ctre
```

然后把 CTRE 的 `include` 目录加进模块的 `module.toml`（路径相对模块目录，
`examples/` 或 `tmp/` 下的模块用 `../../third_party/ctre/include`），
并像其他 libc++ 模块一样 include `libcxx.mk`：

```toml
[build]
cxx_includes = ["../../third_party/ctre/include"]
```

CTRE 的内核入口是 `linuxcpp/include/ctre_kernel.hpp`，完整用法见
[`docs/libcxx.md`](../docs/libcxx.md) 的 CTRE 一节。

## 其他头文件库

没有 STL、异常、RTTI 的头文件库都可以用同样的方式接入：把库的头文件目录写进
`cxx_includes`，需要时用 `cxx_flags` 加库自己的配置宏。内核里没有文件系统、线程
和 locale，依赖这些功能的库即使能编译也无法正常工作。

JSON 库的选择也受这个限制：nlohmann/json、jsoncpp 这类依赖 `std::locale`、
异常和浮点格式化的库不适合。RapidJSON 的 Writer 可以只用整数接口，适合
`sysinfo_json` 这种只输出的场景；Reader 需要浮点，`json_format` 用
`kernel_fpu_begin/end` 显式打开 FPU，并用固定分配器避免在 FPU 区间内睡眠。
