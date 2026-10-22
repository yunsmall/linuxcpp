// SPDX-License-Identifier: GPL-2.0-only

// 设备侧：sensor_device 同时继承内核设备封装和 sensor 业务接口。
// 驱动 probe 只拿到 model::device&，通过 drvdata 取回 sensor*。

#pragma once

#include "device_model.hpp"
#include "sensor.hpp"

namespace sensor_bus_demo {

class sensor_device : public linuxcpp::model::generic_device, public sensor {
public:
	sensor_device(const char *name, linuxcpp::model::bus &bus, sensor_hub &hub);
	~sensor_device() override;

private:
	sensor_hub &hub_;
};

class temperature_sensor final : public sensor_device {
public:
	temperature_sensor(const char *name, linuxcpp::model::bus &bus,
			   sensor_hub &hub, int milli_celsius);

	const char *label() const override;
	const char *unit() const override;
	sensor_kind kind() const override;
	int value() const override;
	void set_value(int value) override;

private:
	int milli_celsius_;
};

class humidity_sensor final : public sensor_device {
public:
	humidity_sensor(const char *name, linuxcpp::model::bus &bus,
			sensor_hub &hub, int milli_percent);

	const char *label() const override;
	const char *unit() const override;
	sensor_kind kind() const override;
	int value() const override;
	void set_value(int value) override;

private:
	int milli_percent_;
};

}  // namespace sensor_bus_demo
