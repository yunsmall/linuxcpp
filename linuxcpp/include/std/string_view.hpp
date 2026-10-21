// SPDX-License-Identifier: GPL-3.0-or-later

// 非拥有字符串视图，避免在内核态依赖 STL。

#pragma once

#include <stddef.h>

namespace linuxcpp {
namespace std {

class string_view {
public:
	static constexpr size_t npos = static_cast<size_t>(-1);

	constexpr string_view() noexcept = default;

	constexpr string_view(const char *data, size_t size) noexcept
		: data_(data), size_(size)
	{
	}

	// 只适用于字符串字面量；普通数组可能没有 '\0' 结尾
	template <size_t N>
	constexpr string_view(const char (&text)[N]) noexcept : data_(text), size_(N - 1)
	{
	}

	constexpr const char *data() const noexcept { return data_; }
	constexpr size_t size() const noexcept { return size_; }
	constexpr bool empty() const noexcept { return size_ == 0; }

	constexpr char operator[](size_t index) const noexcept { return data_[index]; }

	constexpr string_view substr(size_t pos, size_t count = npos) const noexcept
	{
		// 空 view 的 data_ 是 nullptr，nullptr + 0 在标准里也是 UB
		if (data_ == nullptr)
			return string_view();
		if (pos > size_)
			pos = size_;
		size_t left = size_ - pos;
		return string_view(data_ + pos, count < left ? count : left);
	}

	constexpr bool starts_with(string_view other) const noexcept
	{
		return other.size_ <= size_ && equal_at(0, other);
	}

	constexpr bool ends_with(string_view other) const noexcept
	{
		return other.size_ <= size_ && equal_at(size_ - other.size_, other);
	}

	constexpr size_t find(char ch) const noexcept
	{
		for (size_t i = 0; i < size_; ++i)
			if (data_[i] == ch)
				return i;
		return npos;
	}

	constexpr int compare(string_view other) const noexcept
	{
		size_t count = size_ < other.size_ ? size_ : other.size_;
		for (size_t i = 0; i < count; ++i) {
			if (data_[i] < other.data_[i])
				return -1;
			if (data_[i] > other.data_[i])
				return 1;
		}
		if (size_ < other.size_)
			return -1;
		return size_ > other.size_ ? 1 : 0;
	}

private:
	constexpr bool equal_at(size_t pos, string_view other) const noexcept
	{
		for (size_t i = 0; i < other.size_; ++i)
			if (data_[pos + i] != other.data_[i])
				return false;
		return true;
	}

	const char *data_ = nullptr;
	size_t size_ = 0;
};

constexpr bool operator==(string_view left, string_view right) noexcept
{
	return left.compare(right) == 0;
}

constexpr bool operator!=(string_view left, string_view right) noexcept
{
	return left.compare(right) != 0;
}

}  // namespace std
}  // namespace linuxcpp
