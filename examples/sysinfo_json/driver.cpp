// SPDX-License-Identifier: GPL-2.0-only

// 把内核统计信息序列化成 JSON，通过 misc 设备返回。
// 数字全部走整数接口；负载的小数用 RawValue 输出，避免内核里的 double。

#include "linuxcpp.hpp"
#include "device.hpp"
#include "std/mutex.hpp"

#include "stats_kernel.h"

#include <rapidjson/prettywriter.h>
#include <rapidjson/stringbuffer.h>

#include <cstdio>
#include <cstring>
#include <string>

using linuxcpp::abi::iov_iter;
using linuxcpp::abi::kiocb;
using linuxcpp::abi::ssize_t;

namespace {

void write_loadavg(rapidjson::PrettyWriter<rapidjson::StringBuffer> &writer,
		   const struct lc_sys_stats &stats)
{
	writer.Key("loadavg");
	writer.StartArray();
	for (unsigned int value : stats.loadavg_hundredths) {
		char text[16];
		std::snprintf(text, sizeof(text), "%u.%02u", value / 100, value % 100);
		writer.RawValue(text, static_cast<rapidjson::SizeType>(std::strlen(text)),
				rapidjson::kNumberType);
	}
	writer.EndArray();
}

std::string build_json()
{
	struct lc_sys_stats stats;

	lc_collect_sys_stats(&stats);

	rapidjson::StringBuffer buffer;
	rapidjson::PrettyWriter<rapidjson::StringBuffer> writer(buffer);
	writer.SetIndent(' ', 2);

	writer.StartObject();
	writer.Key("kernel");
	writer.String(stats.release);
	writer.Key("hostname");
	writer.String(stats.hostname);
	writer.Key("timestamp");
	writer.Int64(stats.realtime_sec);
	writer.Key("timestamp_nsec");
	writer.Uint(stats.realtime_nsec);
	writer.Key("boot_time");
	writer.Int64(stats.realtime_sec -
		      static_cast<long long>(stats.uptime_ns / 1000000000ULL));
	writer.Key("uptime_seconds");
	writer.Uint64(stats.uptime_ns / 1000000000ULL);
	writer.Key("jiffies");
	writer.Uint64(stats.jiffies);
	writer.Key("page_size");
	writer.Uint64(stats.page_size);
	writer.Key("hz");
	writer.Uint64(stats.hz);
	write_loadavg(writer, stats);

	writer.Key("memory_bytes");
	writer.StartObject();
	writer.Key("total");
	writer.Uint64(stats.totalram_bytes);
	writer.Key("free");
	writer.Uint64(stats.freeram_bytes);
	writer.Key("available");
	writer.Uint64(stats.availableram_bytes);
	writer.Key("shared");
	writer.Uint64(stats.sharedram_bytes);
	writer.Key("buffers");
	writer.Uint64(stats.bufferram_bytes);
	writer.Key("high_total");
	writer.Uint64(stats.totalhigh_bytes);
	writer.Key("high_free");
	writer.Uint64(stats.freehigh_bytes);
	writer.EndObject();

	writer.Key("cpu");
	writer.StartObject();
	writer.Key("online");
	writer.Uint(stats.online_cpus);
	writer.Key("possible");
	writer.Uint(stats.possible_cpus);
	writer.Key("nr_cpu_ids");
	writer.Uint(stats.nr_cpu_ids);
	writer.EndObject();

	writer.Key("tasks");
	writer.StartObject();
	writer.Key("processes");
	writer.Uint(stats.processes);
	writer.Key("threads");
	writer.Uint(stats.threads);
	writer.EndObject();

	writer.EndObject();

	std::string result(buffer.GetString(), buffer.GetSize());
	result += '\n';
	return result;
}

class SysinfoDevice : public linuxcpp::model::misc_device<SysinfoDevice> {
public:
	SysinfoDevice()
		: linuxcpp::model::misc_device<SysinfoDevice>(LCPP_DEVICE_NAME,
							     LCPP_DEVICE_MODE)
	{
	}

	int open(linuxcpp::abi::file *file) override
	{
		(void)file;
		linuxcpp::std::lock_guard guard(mutex_);
		json_ = build_json();
		return 0;
	}

	ssize_t read(kiocb *iocb, iov_iter *to) override
	{
		linuxcpp::std::lock_guard guard(mutex_);
		size_t position = static_cast<size_t>(iocb->ki_pos);

		if (position >= json_.size())
			return 0;

		size_t remaining = json_.size() - position;
		size_t length = remaining < to->count ? remaining : to->count;
		ssize_t copied = static_cast<ssize_t>(
			linuxcpp::abi::lc_copy_to_iter(json_.data() + position, length, to));
		if (copied <= 0 && length != 0)
			return -linuxcpp::abi::EFAULT;
		iocb->ki_pos += copied;
		return copied;
	}

private:
	linuxcpp::std::mutex mutex_;
	std::string json_;
};

SysinfoDevice g_device;

int sysinfo_init(void)
{
	return g_device ? 0 : g_device.error();
}

void sysinfo_exit(void)
{
}

}  // namespace

LCPP_MODULE_RAW(sysinfo_init, sysinfo_exit)
