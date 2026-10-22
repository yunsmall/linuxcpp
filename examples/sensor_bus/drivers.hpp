// SPDX-License-Identifier: GPL-2.0-only

// 驱动侧：总线、驱动基类和两个具体驱动。probe/remove 是 final 模板方法，
// 派生驱动只描述自己接受的传感器类型。

#pragma once

#include "device_model.hpp"
#include "sensor.hpp"

namespace sensor_bus_demo {

class sensor_bus;

class sensor_driver : public linuxcpp::model::bus_driver {
public:
	sensor_driver(const char *name, sensor_bus &bus, sensor_kind kind) noexcept;

	bool accepts(const sensor &item) const { return item.kind() == kind_; }

	int probe(linuxcpp::model::device &dev) final;
	void remove(linuxcpp::model::device &dev) final;

protected:
	virtual const char *description() const = 0;

private:
	class value_attribute final : public linuxcpp::model::attribute {
	public:
		value_attribute();
		void bind(sensor &item);
		linuxcpp::abi::ssize_t show(linuxcpp::model::device &dev,
					    char *buf, size_t size) override;

	private:
		sensor *item_ = nullptr;
	};

	class label_attribute final : public linuxcpp::model::attribute {
	public:
		label_attribute();
		void bind(sensor &item);
		linuxcpp::abi::ssize_t show(linuxcpp::model::device &dev,
					    char *buf, size_t size) override;

	private:
		sensor *item_ = nullptr;
	};

	sensor_kind kind_;
	linuxcpp::model::attribute_group group_{"sensor"};
	value_attribute value_attribute_;
	label_attribute label_attribute_;
};

class sensor_bus final : public linuxcpp::model::bus {
public:
	sensor_bus();
	int match(linuxcpp::model::device &dev,
		  linuxcpp::model::driver &drv) override;
};

class temperature_driver final : public sensor_driver {
public:
	explicit temperature_driver(sensor_bus &bus);

protected:
	const char *description() const override;
};

class humidity_driver final : public sensor_driver {
public:
	explicit humidity_driver(sensor_bus &bus);

protected:
	const char *description() const override;
};

}  // namespace sensor_bus_demo
