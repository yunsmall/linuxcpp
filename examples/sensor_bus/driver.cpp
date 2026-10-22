// SPDX-License-Identifier: GPL-2.0-only

// 模块入口：只负责按顺序构造全局对象并 start 驱动。具体类型分布在
// sensor.cpp、sensor_device.cpp、drivers.cpp 和 monitor.cpp。

#include "drivers.hpp"
#include "monitor.hpp"
#include "sensor_device.hpp"

namespace {

// 声明顺序就是构造顺序：hub -> bus -> 设备 -> monitor -> class。
// rmmod 时 module_exit 先停驱动，再逆序析构，内核不会看到悬空回调。
sensor_bus_demo::sensor_hub g_hub;
sensor_bus_demo::sensor_bus g_bus;
sensor_bus_demo::temperature_driver g_temperature_driver{g_bus};
sensor_bus_demo::humidity_driver g_humidity_driver{g_bus};
sensor_bus_demo::temperature_sensor g_temperature{"temp0", g_bus, g_hub, 21500};
sensor_bus_demo::humidity_sensor g_humidity{"hum0", g_bus, g_hub, 48000};
sensor_bus_demo::sensor_monitor g_monitor{g_hub};
linuxcpp::model::device_class g_device_class{"lcpp_sensor"};

}  // namespace

static int sensor_bus_init(void)
{
	if (!g_bus)
		return g_bus.error();
	if (!g_temperature)
		return g_temperature.error();
	if (!g_humidity)
		return g_humidity.error();
	if (!g_monitor)
		return g_monitor.error();
	if (!g_device_class)
		return g_device_class.error();

	// driver_register 会立即 probe 已有设备，必须等所有全局设备构造完再 start
	int ret = g_temperature_driver.start();

	if (ret)
		return ret;
	ret = g_humidity_driver.start();
	if (ret) {
		g_temperature_driver.stop();
		return ret;
	}
	return 0;
}

static void sensor_bus_exit(void)
{
	g_humidity_driver.stop();
	g_temperature_driver.stop();
}

LCPP_MODULE_RAW(sensor_bus_init, sensor_bus_exit)
