// SPDX-License-Identifier: GPL-2.0-only

// CTRE 的内核入口。
// libc++ 在宽字符关闭时没有 std::wstring_view，但 CTRE 无条件声明了
// 这个重载。这里给一个占位类型让声明通过；内核不支持宽字符匹配，
// 真调用这个重载会在实例化时失败。

#pragma once

#include <cstddef>

namespace std {
struct wstring_view {
	const wchar_t *ptr = nullptr;
	constexpr const wchar_t *begin() const { return ptr; }
	constexpr const wchar_t *end() const { return ptr; }
};
}  // namespace std

#include <ctre.hpp>
