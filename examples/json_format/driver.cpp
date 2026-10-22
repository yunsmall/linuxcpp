// SPDX-License-Identifier: GPL-2.0-only

// ioctl 接收用户空间传来的 JSON 文件 fd，交给 C 侧格式化并原地写回。

#include "linuxcpp.hpp"
#include "device.hpp"

#include "json_format.h"

extern "C" int lc_format_json_fd(int fd);

namespace {

class JsonFormatDevice : public linuxcpp::Device {
public:
	long ioctl(linuxcpp::file *file, unsigned int cmd,
		   unsigned long arg) override
	{
		(void)file;
		if (cmd != LCPP_JSON_FORMAT)
			return -linuxcpp::ENOTTY;
		return lc_format_json_fd(static_cast<int>(arg));
	}
};

JsonFormatDevice g_device;
linuxcpp::misc_device g_misc(&g_device, LCPP_DEVICE_NAME, LCPP_DEVICE_MODE);

int json_format_init(void)
{
	return g_misc.start();
}

void json_format_exit(void)
{
	g_misc.stop();
}

}  // namespace

LCPP_MODULE_RAW(json_format_init, json_format_exit)
