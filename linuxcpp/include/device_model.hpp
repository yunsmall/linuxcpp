// SPDX-License-Identifier: GPL-2.0-only

// 设备模型总入口。只需要字符设备/misc 的模块 include "device.hpp"；
// 用 bus/driver/platform/属性时 include 本文件，并在 module.toml 里写
// [bindings] preset = "device_model"。
//
// 各层分文件：
//   device.hpp         device / char_device<D> / misc_device<D>
//   device_ref.hpp     非拥有设备句柄
//   driver.hpp         驱动抽象基类
//   bus.hpp            自定义总线和 bus_driver
//   generic_device.hpp 挂在 bus 上的通用设备
//   platform.hpp       platform_device / platform_driver
//   attribute.hpp      sysfs 属性和属性组
//   device_class.hpp   struct class

#pragma once

#include "device.hpp"
#include "device_ref.hpp"
#include "driver.hpp"
#include "bus.hpp"
#include "generic_device.hpp"
#include "platform.hpp"
#include "attribute.hpp"
#include "device_class.hpp"
