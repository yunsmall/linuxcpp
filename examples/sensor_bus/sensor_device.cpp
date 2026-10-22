// SPDX-License-Identifier: GPL-2.0-only

#include "sensor_device.hpp"

namespace sensor_bus_demo {

sensor_device::sensor_device(const char *name, linuxcpp::model::bus &bus,
			     sensor_hub &hub)
	: linuxcpp::model::generic_device(name, bus), hub_(hub)
{
	// drvdata 存接口指针：probe 只拿得到 model::device&，不需要知道
	// 设备的具体类型。generic_device 构造时已经注册到内核，但此时驱动
	// 还没 start，不会 probe，所以这里补 drvdata 来得及。
	set_drvdata(static_cast<sensor *>(this));
	hub_.add(*this);
}

sensor_device::~sensor_device()
{
	hub_.remove(*this);
}

temperature_sensor::temperature_sensor(const char *name,
				       linuxcpp::model::bus &bus,
				       sensor_hub &hub, int milli_celsius)
	: sensor_device(name, bus, hub), milli_celsius_(milli_celsius)
{
}

const char *temperature_sensor::label() const
{
	return name();
}

const char *temperature_sensor::unit() const
{
	return "milli-C";
}

sensor_kind temperature_sensor::kind() const
{
	return sensor_kind::temperature;
}

int temperature_sensor::value() const
{
	return milli_celsius_;
}

void temperature_sensor::set_value(int value)
{
	milli_celsius_ = value;
}

humidity_sensor::humidity_sensor(const char *name, linuxcpp::model::bus &bus,
				 sensor_hub &hub, int milli_percent)
	: sensor_device(name, bus, hub), milli_percent_(milli_percent)
{
}

const char *humidity_sensor::label() const
{
	return name();
}

const char *humidity_sensor::unit() const
{
	return "milli-%RH";
}

sensor_kind humidity_sensor::kind() const
{
	return sensor_kind::humidity;
}

int humidity_sensor::value() const
{
	return milli_percent_;
}

void humidity_sensor::set_value(int value)
{
	milli_percent_ = value;
}

}  // namespace sensor_bus_demo
