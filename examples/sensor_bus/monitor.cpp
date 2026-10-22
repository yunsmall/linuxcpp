// SPDX-License-Identifier: GPL-2.0-only

#include "monitor.hpp"

#include <stdio.h>
#include <stdlib.h>

namespace sensor_bus_demo {

using linuxcpp::abi::iov_iter;
using linuxcpp::abi::kiocb;
using linuxcpp::abi::ssize_t;

sensor_monitor::sensor_monitor(sensor_hub &hub)
	: linuxcpp::model::misc_device<sensor_monitor>("sensor_monitor", 0666),
	  hub_(hub)
{
}

ssize_t sensor_monitor::read(kiocb *iocb, iov_iter *to)
{
	char buf[512];
	size_t used = 0;

	for (unsigned i = 0; i < hub_.size(); ++i) {
		sensor *item = hub_.at(i);
		int written = snprintf(buf + used, sizeof(buf) - used,
				       "%s=%d %s\n", item->label(), item->value(),
				       item->unit());

		if (written < 0)
			return -linuxcpp::abi::EINVAL;
		if (static_cast<size_t>(written) >= sizeof(buf) - used)
			break;
		used += static_cast<size_t>(written);
	}

	auto offset = static_cast<size_t>(iocb->ki_pos);

	if (offset >= used)
		return 0;

	size_t length = used - offset;

	if (length > to->count)
		length = to->count;

	ssize_t copied = static_cast<ssize_t>(
		linuxcpp::abi::lc_copy_to_iter(buf + offset, length, to));

	if (copied > 0)
		iocb->ki_pos += copied;
	return copied;
}

ssize_t sensor_monitor::write(kiocb *iocb, iov_iter *from)
{
	char buf[64];
	size_t count = linuxcpp::abi::lc_copy_from_iter(buf, sizeof(buf) - 1,
							from);

	if (count == 0)
		return -linuxcpp::abi::EINVAL;
	buf[count] = '\0';

	char *label = buf;

	while (*label == ' ' || *label == '\t')
		++label;

	char *cursor = label;

	while (*cursor && *cursor != ' ' && *cursor != '\t' && *cursor != '=' &&
	       *cursor != '\n')
		++cursor;
	if (!*cursor)
		return -linuxcpp::abi::EINVAL;
	*cursor++ = '\0';
	while (*cursor == ' ' || *cursor == '\t' || *cursor == '=')
		++cursor;

	char *end = nullptr;
	long value = strtol(cursor, &end, 10);

	if (end == cursor)
		return -linuxcpp::abi::EINVAL;

	sensor *item = hub_.find(label);

	if (!item)
		return -linuxcpp::abi::ENOENT;

	item->set_value(static_cast<int>(value));
	iocb->ki_pos += static_cast<decltype(iocb->ki_pos)>(count);
	return static_cast<ssize_t>(count);
}

}  // namespace sensor_bus_demo
