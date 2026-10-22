// SPDX-License-Identifier: GPL-2.0-only

// 传感器业务接口和注册表。这里不依赖任何内核类型，设备、驱动和
// 监控设备都只通过这个接口互相看见。

#pragma once

namespace sensor_bus_demo {

enum class sensor_kind {
	temperature,
	humidity,
};

class sensor {
public:
	virtual ~sensor() = default;

	virtual const char *label() const = 0;
	virtual const char *unit() const = 0;
	virtual sensor_kind kind() const = 0;
	virtual int value() const = 0;
	virtual void set_value(int value) = 0;
};

class sensor_hub {
public:
	static constexpr unsigned kMaxSensors = 8;

	bool add(sensor &item);
	void remove(sensor &item);
	unsigned size() const;
	sensor *at(unsigned index) const;
	sensor *find(const char *label) const;

private:
	static bool equal(const char *left, const char *right);

	sensor *items_[kMaxSensors]{};
	unsigned count_ = 0;
};

}  // namespace sensor_bus_demo
