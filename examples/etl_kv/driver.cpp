// SPDX-License-Identifier: GPL-2.0-only

// ETL 固定容量容器示例：一个内存键值存储。
//   echo "set name linuxcpp" > /dev/etl_kv
//   echo "get name" > /dev/etl_kv && cat /dev/etl_kv
//   echo "list" > /dev/etl_kv && cat /dev/etl_kv

#include "linuxcpp.hpp"

#include <etl/map.h>
#include <etl/string.h>
#include <etl/vector.h>

using linuxcpp::iov_iter;
using linuxcpp::kiocb;
using linuxcpp::ssize_t;

namespace {

using key_type = etl::string<32>;
using value_type = etl::string<64>;
using store_type = etl::map<key_type, value_type, 16>;

linuxcpp::std::unique_ptr<store_type> g_store;
linuxcpp::std::unique_ptr<etl::string<512>> g_output;
linuxcpp::std::unique_ptr<linuxcpp::std::mutex> g_lock;

void append(etl::string<512> &out, const char *text, size_t size)
{
	out.append(text, size);
}

void handle_command(const etl::string<128> &line)
{
	etl::vector<etl::string<32>, 4> parts;
	size_t i = 0;
	while (i < line.size() && parts.size() < parts.max_size()) {
		while (i < line.size() && (line[i] == ' ' || line[i] == '\t'))
			++i;
		size_t start = i;
		while (i < line.size() && line[i] != ' ' && line[i] != '\t')
			++i;
		if (i > start)
			parts.push_back(etl::string<32>(line.data() + start, i - start));
	}

	g_output->clear();
	if (parts.empty())
		return;

	if (parts[0] == "set" && parts.size() >= 3) {
		(*g_store)[parts[1]] = value_type(parts[2].data(), parts[2].size());
		append(*g_output, "ok\n", 3);
	} else if (parts[0] == "get" && parts.size() >= 2) {
		auto it = g_store->find(parts[1]);
		if (it == g_store->end()) {
			append(*g_output, "not found\n", 10);
		} else {
			append(*g_output, it->first.data(), it->first.size());
			append(*g_output, "=", 1);
			append(*g_output, it->second.data(), it->second.size());
			append(*g_output, "\n", 1);
		}
	} else if (parts[0] == "del" && parts.size() >= 2) {
		if (g_store->erase(parts[1]) > 0)
			append(*g_output, "deleted\n", 8);
		else
			append(*g_output, "not found\n", 10);
	} else if (parts[0] == "clear") {
		g_store->clear();
		append(*g_output, "cleared\n", 8);
	} else if (parts[0] == "list") {
		for (auto &kv : *g_store) {
			append(*g_output, kv.first.data(), kv.first.size());
			append(*g_output, "=", 1);
			append(*g_output, kv.second.data(), kv.second.size());
			append(*g_output, "\n", 1);
		}
	} else {
		static constexpr char usage[] =
			"usage: set <key> <value> | get <key> | del <key> | list | clear\n";
		append(*g_output, usage, sizeof(usage) - 1);
	}
}

ssize_t kv_read(kiocb *iocb, iov_iter *to)
{
	linuxcpp::std::lock_guard guard(*g_lock);
	const size_t length = g_output->size();
	size_t pos = static_cast<size_t>(iocb->ki_pos);

	if (pos >= length)
		return 0;
	ssize_t n = static_cast<ssize_t>(
		linuxcpp::lc_copy_to_iter(g_output->data() + pos, length - pos, to));
	// copy_to_iter 返回 0 而用户缓冲区还有空间，说明目标地址不可写，不能当 EOF
	if (n == 0 && to->count != 0)
		return -linuxcpp::EFAULT;
	iocb->ki_pos += n;
	return n;
}

ssize_t kv_write(kiocb *iocb, iov_iter *from)
{
	char buffer[128];
	size_t total = linuxcpp::lc_copy_from_iter(buffer, sizeof(buffer), from);
	if (total == 0)
		return -linuxcpp::EFAULT;

	size_t length = total;
	while (length > 0 && (buffer[length - 1] == '\n' || buffer[length - 1] == '\r'))
		--length;
	etl::string<128> line(buffer, length);
	{
		linuxcpp::std::lock_guard guard(*g_lock);
		handle_command(line);
	}
	iocb->ki_pos += total;
	return static_cast<ssize_t>(total);
}

const linuxcpp::file_operations kv_fops = {
	.owner = linuxcpp::this_module(),
	.read_iter = kv_read,
	.write_iter = kv_write,
};

linuxcpp::miscdevice kv_misc = {
	.minor = linuxcpp::MISC_DYNAMIC_MINOR,
	.name = LCPP_DEVICE_NAME,
	.fops = &kv_fops,
	.mode = LCPP_DEVICE_MODE,
};

int kv_init(void)
{
	g_lock.reset(new linuxcpp::std::mutex());
	g_store.reset(new store_type());
	g_output.reset(new etl::string<512>());
	if (!g_lock || !g_lock->ok() || !g_store || !g_output)
		goto fail;

	if (linuxcpp::misc_register(&kv_misc) != 0)
		goto fail;
	return 0;

fail:
	g_output.reset();
	g_store.reset();
	g_lock.reset();
	return -linuxcpp::ENOMEM;
}

void kv_exit(void)
{
	linuxcpp::misc_deregister(&kv_misc);
	g_output.reset();
	g_store.reset();
	g_lock.reset();
}

}  // namespace

LCPP_MODULE_RAW(kv_init, kv_exit)
