# 设备模型 C++ 面向对象层

Linux 用 `struct device` 嵌入、函数指针和 `container_of` 实现 C 面向对象。
`linuxcpp::model` 把这些关系翻成真正的 C++ 继承和虚函数：

```text
model::device                     struct device 的 C++ 基类（kernel/name）
  ├── model::char_device<D>       open/read/write/ioctl = file_operations
  │     └── model::misc_device<D> misc 设备，构造注册/析构注销
  ├── model::device_ref           非拥有句柄
  ├── model::generic_device       挂在自定义 bus 上的通用设备
  └── model::platform_device      platform 设备

model::driver                     抽象驱动基类
  ├── model::bus_driver           挂在自定义 bus 上
  └── model::platform_driver      platform 驱动

model::bus                        自定义总线
model::device_class               struct class
model::attribute                  单个 sysfs 属性
model::attribute_group            固定容量属性组
```

内核 ABI 镜像（`struct device`、`file_operations`、`miscdevice` 等）在
`linuxcpp::abi`，只由 `bindings.hpp` 生成；C++ 类在 `linuxcpp::model`，两者
不互相替代。

`char_device` / `misc_device` 用 CRTP 拿到最终设备类型（`Derived`）。
派生类覆盖了 `read`/`write`/`ioctl` 中的哪个，基类就用 `&Derived::method`
和 `&char_device::method` 的成员指针类型差异在编译期判断出来，只给覆盖过的
操作装 trampoline；没覆盖的保持 `NULL`，和 Rust `#[vtable]` 的效果一致。
`open`/`release` 始终安装，因为 `open` 负责把对象指针放进 `file->private_data`。
参与检测的虚函数必须是 public，且不要对同名 fops 方法加重载。

## 文件

| 文件 | 内容 |
|---|---|
| `device.hpp` | `device`、`char_device<D>`、`misc_device<D>` |
| `device_ref.hpp` | 非拥有设备句柄 |
| `driver.hpp` | 驱动抽象基类 |
| `bus.hpp` | `bus`、`bus_driver` |
| `generic_device.hpp` | 挂在 bus 上的通用设备 |
| `platform.hpp` | `platform_device`、`platform_device_ref`、`platform_driver` |
| `attribute.hpp` | `attribute`、`attribute_group` |
| `device_class.hpp` | `device_class` |
| `device_model.hpp` | 以上所有头的总入口 |

字符设备只需要 include `device.hpp`；用 bus/driver/platform 时 include
`device_model.hpp`，并在 `module.toml` 里写：

```toml
[bindings]
preset = "device_model"
```

preset 会加入 device/driver/bus/class/platform 等 roots、导出函数、headers
和 `PAGE_SIZE`。

## 注册时机

- `misc_device<D>`、`bus`、`generic_device`、`platform_device`、`device_class`
  在构造函数里注册，析构函数里注销。构造失败不会抛异常，检查 `error()` 或
  `explicit operator bool()`。
- `bus_driver`、`platform_driver` 必须显式 `start()` / `stop()`。
  `driver_register` 可能立刻 probe 已有设备，如果放在构造函数里，派生类还没
  构造完就会回调虚函数。
- 所有 owning 类型都禁止拷贝和移动：对象地址会被内核链表和 sysfs 引用。

回调接口对象（用户自己继承的对象）必须比对应注册对象活得久；全局对象按声明
顺序构造、逆序析构，正好满足。

## 回调怎么回到 C++

每个多态类内部都有一个标准布局的 holder：内核结构 + `owner` 指针。内核回调
是静态 trampoline，从内核结构反查 holder，再调用 `owner` 的虚函数。例如
`bus_type.match` → `bus::match`，`platform_driver.probe` →
`platform_driver::probe(platform_device_ref&)`。

`remove` 的返回类型在不同内核里是 `void` 或 `int`，用
`callback_result.hpp` 里的 `function_result` / `zero_return` 按镜像成员的
真实类型做编译期适配。

## file_operations

`char_device` 的虚函数就是 `file_operations`：

```cpp
class MyDevice : public linuxcpp::model::misc_device<MyDevice> {
public:
    MyDevice() : misc_device<MyDevice>("mydev", 0666) {}

    linuxcpp::abi::ssize_t read(linuxcpp::abi::kiocb *iocb,
                                linuxcpp::abi::iov_iter *to) override;
};
```

`char_device` 在私有 holder 里放一份 `abi::file_operations`，并把它交给
`misc_register`。不需要手写 fops 表；这个例子只覆盖了 `read`，所以
`read_iter` 有 trampoline，`write_iter` 和 `unlocked_ioctl` 保持 `NULL`。

## 示例

`examples/device_model` 同时注册：

- 一个自定义 bus、bus_driver 和 generic_device；
- 一个 platform_driver 和 platform_device；
- 一个继承 `attribute` 的 sysfs 属性。

```bash
make -C examples/device_model -j6
sudo insmod examples/device_model/device_model.ko
python3 examples/device_model/test.py
cat /sys/bus/lcpp_demo/devices/lcpp_demo0/demo
sudo rmmod device_model
```

`examples/sensor_bus` 在此基础上演示更完整的 C++ 面向对象写法：

- `sensor` 是纯虚业务接口（`label/unit/kind/value/set_value`），和内核类型无关；
- `sensor_device` 同时继承 `model::generic_device` 和 `sensor`，构造时把
  `sensor *` 放进 `driver_data`；
- `sensor_bus::match()` 用 `model::device::drvdata()` 取回接口指针，再调用驱动的
  `accepts()` 虚函数决定绑定关系；
- `sensor_driver::probe/remove` 是 `final` 模板方法，派生驱动只实现
  `description()`；
- 每个驱动在 probe 时挂一个 `attribute_group`，show 通过 `sensor` 接口取值；
- `/dev/sensor_monitor` 也是 `misc_device<sensor_monitor>` 子类，read/write
  全部通过 `sensor` 接口遍历和修改传感器。

示例按职责拆成 `sensor.*`（接口和注册表）、`sensor_device.*`（设备）、
`drivers.*`（总线和驱动）、`monitor.*`（misc 设备）和 `driver.cpp`（入口）。
Makefile 用 kbuild 的方式显式声明对象列表：

```make
obj-m := sensor_bus.o
sensor_bus-y := driver.o drivers.o monitor.o sensor.o sensor_device.o
```

构建器只按列表找同名 `.cpp`，不扫描目录；新增文件时把对象加进
`sensor_bus-y`。

```bash
make -C examples/sensor_bus -j6
sudo insmod examples/sensor_bus/sensor_bus.ko
python3 examples/sensor_bus/test.py
cat /dev/sensor_monitor
sudo rmmod sensor_bus
```

目前只在 `6.18.33.1-microsoft-standard-WSL2` 上实际加载验证过；其他内核版本需要
重新生成绑定并自行验证。
