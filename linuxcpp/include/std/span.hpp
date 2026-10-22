// SPDX-License-Identifier: GPL-2.0-only

// 指针 + 长度视图，不拥有内存。

#pragma once

#include <stddef.h>

namespace linuxcpp {
namespace std {

template <typename T>
class span {
public:
	span() noexcept = default;
	span(T *data, size_t size) noexcept : data_(data), size_(size) {}

	T *data() const noexcept { return data_; }
	size_t size() const noexcept { return size_; }
	bool empty() const noexcept { return size_ == 0; }
	T &operator[](size_t index) const noexcept { return data_[index]; }

	T *begin() const noexcept { return data_; }
	T *end() const noexcept { return data_ + size_; }
	T &front() const noexcept { return data_[0]; }
	T &back() const noexcept { return data_[size_ - 1]; }

	span subspan(size_t offset, size_t count) const noexcept
	{
		// 越界输入夹到合法范围；空 span 的 data_ 可能是 nullptr，
		// 不能对它做指针算术
		if (data_ == nullptr)
			return span();
		if (offset > size_)
			offset = size_;
		size_t left = size_ - offset;
		return span(data_ + offset, count < left ? count : left);
	}

private:
	T *data_ = nullptr;
	size_t size_ = 0;
};

}  // namespace std
}  // namespace linuxcpp
