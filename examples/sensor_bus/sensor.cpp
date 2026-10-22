// SPDX-License-Identifier: GPL-2.0-only

#include "sensor.hpp"

namespace sensor_bus_demo {

bool sensor_hub::add(sensor &item)
{
	if (count_ >= kMaxSensors)
		return false;
	items_[count_++] = &item;
	return true;
}

void sensor_hub::remove(sensor &item)
{
	for (unsigned i = 0; i < count_; ++i) {
		if (items_[i] != &item)
			continue;
		items_[i] = items_[--count_];
		return;
	}
}

unsigned sensor_hub::size() const
{
	return count_;
}

sensor *sensor_hub::at(unsigned index) const
{
	return index < count_ ? items_[index] : nullptr;
}

sensor *sensor_hub::find(const char *label) const
{
	if (!label)
		return nullptr;

	for (unsigned i = 0; i < count_; ++i) {
		if (equal(items_[i]->label(), label))
			return items_[i];
	}
	return nullptr;
}

bool sensor_hub::equal(const char *left, const char *right)
{
	if (!left || !right)
		return false;
	while (*left && *left == *right) {
		++left;
		++right;
	}
	return *left == *right;
}

}  // namespace sensor_bus_demo
