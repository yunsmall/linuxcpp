// SPDX-License-Identifier: GPL-2.0-only

#include "drivers.hpp"

#include <stdio.h>

namespace sensor_bus_demo {

sensor_driver::value_attribute::value_attribute()
	: linuxcpp::model::attribute("value", 0444)
{
}

void sensor_driver::value_attribute::bind(sensor &item)
{
	item_ = &item;
}

linuxcpp::abi::ssize_t
sensor_driver::value_attribute::show(linuxcpp::model::device &dev, char *buf,
				     size_t size)
{
	(void)dev;
	if (!item_)
		return -linuxcpp::abi::ENODEV;
	return static_cast<linuxcpp::abi::ssize_t>(
		snprintf(buf, size, "%d %s\n", item_->value(), item_->unit()));
}

sensor_driver::label_attribute::label_attribute()
	: linuxcpp::model::attribute("label", 0444)
{
}

void sensor_driver::label_attribute::bind(sensor &item)
{
	item_ = &item;
}

linuxcpp::abi::ssize_t
sensor_driver::label_attribute::show(linuxcpp::model::device &dev, char *buf,
				     size_t size)
{
	(void)dev;
	if (!item_)
		return -linuxcpp::abi::ENODEV;
	return static_cast<linuxcpp::abi::ssize_t>(
		snprintf(buf, size, "%s (%s)\n", item_->label(), item_->unit()));
}

sensor_driver::sensor_driver(const char *name, sensor_bus &bus,
			     sensor_kind kind) noexcept
	: linuxcpp::model::bus_driver(name, bus), kind_(kind)
{
	group_.add(value_attribute_);
	group_.add(label_attribute_);
}

int sensor_driver::probe(linuxcpp::model::device &dev)
{
	// 总线 trampoline 把 struct device* 包成 device_ref，这里按约定取回
	// 设备构造时存入的 sensor 接口
	auto *item = static_cast<sensor *>(
		static_cast<linuxcpp::model::device_ref &>(dev).drvdata());

	if (!item)
		return -linuxcpp::abi::ENODEV;

	value_attribute_.bind(*item);
	label_attribute_.bind(*item);

	int ret = group_.attach(dev);

	if (ret)
		return ret;
	linuxcpp::printk("sensor_bus: %s probed by %s\n", item->label(),
			 description());
	return 0;
}

void sensor_driver::remove(linuxcpp::model::device &dev)
{
	group_.detach(dev);
}

sensor_bus::sensor_bus() : linuxcpp::model::bus("lcpp_sensor")
{
}

int sensor_bus::match(linuxcpp::model::device &dev,
		      linuxcpp::model::driver &drv)
{
	auto *item = static_cast<sensor *>(
		static_cast<linuxcpp::model::device_ref &>(dev).drvdata());

	if (!item)
		return 0;
	// 这条总线只接受 sensor_driver，由驱动判断传感器类型
	return static_cast<sensor_driver &>(drv).accepts(*item);
}

temperature_driver::temperature_driver(sensor_bus &bus)
	: sensor_driver("sensor-temp", bus, sensor_kind::temperature)
{
}

const char *temperature_driver::description() const
{
	return "temperature driver";
}

humidity_driver::humidity_driver(sensor_bus &bus)
	: sensor_driver("sensor-hum", bus, sensor_kind::humidity)
{
}

const char *humidity_driver::description() const
{
	return "humidity driver";
}

}  // namespace sensor_bus_demo
