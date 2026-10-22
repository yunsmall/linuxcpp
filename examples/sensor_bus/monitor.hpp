// SPDX-License-Identifier: GPL-2.0-only

// /dev/sensor_monitor：字符设备的 read/write 直接通过 sensor 接口
// 遍历和修改传感器，不依赖任何具体设备或驱动类型。

#pragma once

#include "device_model.hpp"
#include "sensor.hpp"

namespace sensor_bus_demo {

class sensor_monitor final
	: public linuxcpp::model::misc_device<sensor_monitor> {
public:
	explicit sensor_monitor(sensor_hub &hub);

	linuxcpp::abi::ssize_t read(linuxcpp::abi::kiocb *iocb,
				    linuxcpp::abi::iov_iter *to) override;
	linuxcpp::abi::ssize_t write(linuxcpp::abi::kiocb *iocb,
				     linuxcpp::abi::iov_iter *from) override;

private:
	sensor_hub &hub_;
};

}  // namespace sensor_bus_demo
