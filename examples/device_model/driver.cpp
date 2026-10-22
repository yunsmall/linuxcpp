// SPDX-License-Identifier: GPL-2.0-only

// 设备模型 C++ 面向对象演示：继承 bus / bus_driver / platform_driver，
// 实现 probe/remove 虚函数；sysfs 属性继承 attribute。

#include <stdio.h>

#include "device_model.hpp"

using namespace linuxcpp;

namespace {

class demo_attribute : public model::attribute {
public:
	demo_attribute() : model::attribute("demo", 0444) {}

	linuxcpp::abi::ssize_t show(model::device &dev, char *buf, size_t size) override
	{
		(void)dev;
		return snprintf(buf, size, "C++ device model works\n");
	}
};

class demo_bus : public model::bus {
public:
	demo_bus() : model::bus("lcpp_demo") {}

	int match(model::device &dev, model::driver &drv) override
	{
		(void)dev;
		(void)drv;
		return 1;
	}
};

class demo_driver : public model::bus_driver {
public:
	explicit demo_driver(demo_bus &bus) : model::bus_driver("lcpp_demo", bus) {}

	int probe(model::device &dev) override
	{
		printk("device_model: probe %s\n",
		       dev.name() ? dev.name() : "(null)");
		return attr_.attach(dev);
	}

	void remove(model::device &dev) override
	{
		attr_.detach(dev);
		printk("device_model: remove %s\n",
		       dev.name() ? dev.name() : "(null)");
	}

private:
	demo_attribute attr_;
};

class demo_device : public model::generic_device {
public:
	explicit demo_device(demo_bus &bus)
		: model::generic_device("lcpp_demo0", bus)
	{
	}
};

class demo_platform_driver : public model::platform_driver {
public:
	demo_platform_driver() : model::platform_driver("lcpp_platform_demo") {}

	int probe(model::platform_device_ref &pdev) override
	{
		printk("device_model: platform probe %s.%d\n",
		       pdev.name() ? pdev.name() : "(null)", pdev.id());
		return 0;
	}

	void remove(model::platform_device_ref &pdev) override
	{
		printk("device_model: platform remove %s.%d\n",
		       pdev.name() ? pdev.name() : "(null)", pdev.id());
	}
};

// 同一个翻译单元里按声明顺序构造、逆序析构
demo_bus g_bus;
demo_driver g_driver{g_bus};
demo_device g_device{g_bus};
demo_platform_driver g_platform_driver;
model::platform_device g_platform_device{"lcpp_platform_demo", 0};

}  // namespace

static int demo_init(void)
{
	if (!g_bus)
		return g_bus.error();
	if (!g_device)
		return g_device.error();

	// 驱动必须显式 start：driver_register 可能立刻 probe，
	// 构造函数里注册会在派生类构造完成前回调虚函数
	int ret = g_driver.start();

	if (ret)
		return ret;
	ret = g_platform_driver.start();
	if (ret) {
		g_driver.stop();
		return ret;
	}
	return 0;
}

static void demo_exit(void)
{
	// 析构里还会再 stop 一次，stop 是幂等的
	g_platform_driver.stop();
	g_driver.stop();
}

LCPP_MODULE_RAW(demo_init, demo_exit)
