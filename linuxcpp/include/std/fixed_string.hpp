// SPDX-License-Identifier: GPL-2.0-only

// 固定容量字符串：数据放在对象内部，不依赖堆分配。

#pragma once

#include <stddef.h>

#include "string_view.hpp"

namespace linuxcpp {
namespace std {

template <size_t Capacity>
class fixed_string {
public:
	fixed_string() noexcept : data_{}, size_(0) {}

	explicit fixed_string(string_view text) noexcept { assign(text); }
	explicit fixed_string(const char *text) noexcept { assign(text); }

	// 返回 false 表示输入被截断
	bool assign(const char *text) noexcept
	{
		if (text == nullptr) {
			data_[0] = '\0';
			size_ = 0;
			return false;
		}
		size_t count = 0;
		while (count < Capacity && text[count] != '\0') {
			data_[count] = text[count];
			++count;
		}
		bool complete = text[count] == '\0';
		data_[count] = '\0';
		size_ = count;
		return complete;
	}

	bool assign(string_view text) noexcept
	{
		size_t count = text.size() < Capacity ? text.size() : Capacity;
		for (size_t i = 0; i < count; ++i)
			data_[i] = text[i];
		data_[count] = '\0';
		size_ = count;
		return text.size() <= Capacity;
	}

	const char *c_str() const noexcept { return data_; }
	char *data() noexcept { return data_; }
	size_t size() const noexcept { return size_; }
	bool empty() const noexcept { return size_ == 0; }

	string_view view() const noexcept { return string_view(data_, size_); }

	char &operator[](size_t index) noexcept { return data_[index]; }
	const char &operator[](size_t index) const noexcept { return data_[index]; }

private:
	char data_[Capacity + 1];
	size_t size_;
};

}  // namespace std
}  // namespace linuxcpp
