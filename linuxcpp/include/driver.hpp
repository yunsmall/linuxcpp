// SPDX-License-Identifier: GPL-2.0-only

// 驱动抽象基类。内核的 struct device_driver 用函数指针做回调；
// 这里换成虚函数，具体总线驱动继承它并实现 probe/remove/shutdown。

#pragma once

#include "device.hpp"

namespace linuxcpp {
namespace model {

class driver {
public:
	virtual ~driver() = default;

	virtual int probe(device &dev) = 0;
	virtual void remove(device &dev) { (void)dev; }
	virtual void shutdown(device &dev) { (void)dev; }

	// driver_register 可能立刻 probe 已有设备，而派生类还没构造完；
	// 所以驱动不能用构造注册，必须显式 start()
	[[nodiscard]] virtual int start() = 0;
	virtual void stop() = 0;

	virtual abi::device_driver *kernel() = 0;

	[[nodiscard]] int error() const noexcept { return error_; }
	explicit operator bool() const noexcept { return error_ == 0; }

protected:
	int error_ = -abi::EINVAL;
};

}  // namespace model
}  // namespace linuxcpp
