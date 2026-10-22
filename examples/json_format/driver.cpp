// SPDX-License-Identifier: GPL-2.0-only

// ioctl 接收用户空间传来的 JSON 文件 fd，交给 C 侧格式化并原地写回。

#include "linuxcpp.hpp"
#include "device.hpp"

#include "json_format.h"

extern "C" int lc_format_json_fd(int fd);

namespace {

class JsonFormatDevice
	: public linuxcpp::model::misc_device<JsonFormatDevice> {
public:
	JsonFormatDevice()
		: linuxcpp::model::misc_device<JsonFormatDevice>(LCPP_DEVICE_NAME,
								 LCPP_DEVICE_MODE)
	{
	}

	long ioctl(linuxcpp::abi::file *file, unsigned int cmd,
		   unsigned long arg) override
	{
		(void)file;
		if (cmd != LCPP_JSON_FORMAT)
			return -linuxcpp::abi::ENOTTY;
		return lc_format_json_fd(static_cast<int>(arg));
	}
};

JsonFormatDevice g_device;

int json_format_init(void)
{
	return g_device ? 0 : g_device.error();
}

void json_format_exit(void)
{
}

}  // namespace

LCPP_MODULE_RAW(json_format_init, json_format_exit)
