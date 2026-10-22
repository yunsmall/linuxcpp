// SPDX-License-Identifier: GPL-2.0-only

// 固定大小数组，带上界明确的 size()/data()。

#pragma once

#include <stddef.h>

namespace linuxcpp {
namespace std {

template <typename T, size_t N>
class array {
public:
	T &operator[](size_t index) noexcept { return data_[index]; }
	const T &operator[](size_t index) const noexcept { return data_[index]; }
	constexpr size_t size() const noexcept { return N; }
	T *data() noexcept { return data_; }
	const T *data() const noexcept { return data_; }
	T *begin() noexcept { return data_; }
	const T *begin() const noexcept { return data_; }
	T *end() noexcept { return data_ + N; }
	const T *end() const noexcept { return data_ + N; }
	T &front() noexcept { return data_[0]; }
	const T &front() const noexcept { return data_[0]; }
	T &back() noexcept { return data_[N - 1]; }
	const T &back() const noexcept { return data_[N - 1]; }

private:
	T data_[N];
};

}  // namespace std
}  // namespace linuxcpp
