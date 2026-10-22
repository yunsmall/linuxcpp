// SPDX-License-Identifier: GPL-2.0-only

// libc++ 内核移植验证：标准库直接可用的设施在内核里实际跑一遍。

#include "linuxcpp.hpp"

#include <algorithm>
#include <any>
#include <array>
#include <atomic>
#include <bitset>
#include <charconv>
#include <chrono>
#include <deque>
#include <forward_list>
#include <functional>
#include <list>
#include <map>
#include <memory>
#include <numeric>
#include <optional>
#include <set>
#include <span>
#include <string>
#include <string_view>
#include <system_error>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <variant>
#include <vector>

using linuxcpp::abi::iov_iter;
using linuxcpp::abi::kiocb;
using linuxcpp::abi::ssize_t;

namespace {

std::string g_message;

ssize_t demo_read(kiocb *iocb, iov_iter *to)
{
	const size_t length = g_message.size();
	size_t pos = static_cast<size_t>(iocb->ki_pos);

	if (pos >= length)
		return 0;
	ssize_t n = static_cast<ssize_t>(
		linuxcpp::abi::lc_copy_to_iter(g_message.data() + pos, length - pos, to));
	if (n == 0 && to->count != 0)
		return -linuxcpp::abi::EFAULT;
	iocb->ki_pos += n;
	return n;
}

ssize_t demo_write(kiocb *iocb, iov_iter *from)
{
	char buffer[64];
	ssize_t n = static_cast<ssize_t>(
		linuxcpp::abi::lc_copy_from_iter(buffer, sizeof(buffer) - 1, from));
	buffer[n < 0 ? 0 : n] = '\0';
	iocb->ki_pos += n;
	g_message = buffer;
	return n;
}

const linuxcpp::abi::file_operations demo_fops = {
	.owner = linuxcpp::this_module(),
	.read_iter = demo_read,
	.write_iter = demo_write,
};

linuxcpp::abi::miscdevice demo_misc = {
	.minor = linuxcpp::abi::MISC_DYNAMIC_MINOR,
	.name = LCPP_DEVICE_NAME,
	.fops = &demo_fops,
	.mode = LCPP_DEVICE_MODE,
};

template <typename T>
void append_value(std::string &out, const char *name, T value)
{
	out += name;
	out += '=';
	out += std::to_string(value);
	out += ' ';
}

void run_containers(std::string &out)
{
	std::map<std::string, int> map;
	map["alpha"] = 1;
	std::set<int> set;
	set.insert(2);
	std::unordered_set<std::string> uset;
	uset.insert("x");
	std::list<int> list;
	list.push_back(3);
	std::deque<int> deque;
	deque.push_back(4);
	std::forward_list<int> flist;
	flist.push_front(5);

	std::vector<int> values{5, 3, 1, 4, 2};
	std::ranges::sort(values);
	auto found = std::ranges::find(values, 3);

	out += "containers:";
	append_value(out, "map", map["alpha"]);
	append_value(out, "set", *set.begin());
	append_value(out, "uset", uset.size());
	append_value(out, "list", list.front());
	append_value(out, "deque", deque.front());
	append_value(out, "flist", *flist.begin());
	append_value(out, "vector", *found);
	out += '\n';
}

void run_views(std::string &out)
{
	std::optional<int> optional = 3;
	std::variant<int, std::string> variant = std::string("x");
	std::any any = 42;
	std::span<const int> span;
	const int numbers[] = {7, 8, 9};
	span = std::span<const int>(numbers);
	std::string_view view = "libcxx";
	auto shared = std::make_shared<int>(1);
	auto unique = std::make_unique<int>(2);

	out += "views:";
	append_value(out, "optional", *optional);
	out += "variant=";
	out += std::get<std::string>(variant);
	out += ' ';
	append_value(out, "any", std::any_cast<int>(any));
	append_value(out, "span", span.size());
	append_value(out, "find", view.find('c'));
	append_value(out, "shared", *shared);
	append_value(out, "unique", *unique);
	out += '\n';
}

void run_utilities(std::string &out)
{
	std::error_code ec = std::make_error_code(std::errc::invalid_argument);
	std::function<int(int)> fn = [](int value) { return value + 1; };
	std::array<int, 3> array{1, 2, 3};
	std::tuple<int, int> tuple{4, 5};
	std::bitset<8> bits;
	bits.set(1);
	std::atomic<int> counter{0};
	counter.fetch_add(1);

	char buffer[32];
	auto converted = std::to_chars(buffer, buffer + sizeof(buffer), 12345);
	int parsed = 0;
	std::from_chars(buffer, converted.ptr, parsed);

	out += "utilities:";
	append_value(out, "ec", static_cast<int>(ec.value()));
	out += "ecmsg=";
	out += ec.message();
	out += ' ';
	append_value(out, "function", fn(1));
	append_value(out, "array", std::accumulate(array.begin(), array.end(), 0));
	append_value(out, "tuple", std::get<1>(tuple));
	append_value(out, "bitset", bits.count());
	append_value(out, "atomic", counter.load());
	append_value(out, "to_chars", parsed);
	out += '\n';
}

void run_chrono(std::string &out)
{
	auto real = std::chrono::system_clock::now();
	auto mono_start = std::chrono::steady_clock::now();
	auto mono_end = std::chrono::steady_clock::now();

	auto epoch = std::chrono::duration_cast<std::chrono::seconds>(
		real.time_since_epoch()).count();
	auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
		mono_end - mono_start).count();

	out += "chrono:";
	append_value(out, "epoch", epoch);
	append_value(out, "steady_us", elapsed);
	out += '\n';
}

int demo_init(void)
{
	std::string text;
	run_containers(text);
	run_views(text);
	run_utilities(text);
	run_chrono(text);
	g_message = std::move(text);

	linuxcpp::printk("%s", g_message.c_str());
	return linuxcpp::abi::misc_register(&demo_misc);
}

void demo_exit(void)
{
	linuxcpp::printk("std_demo: exit\n");
	linuxcpp::abi::misc_deregister(&demo_misc);
}

}  // namespace

LCPP_MODULE_RAW(demo_init, demo_exit)
