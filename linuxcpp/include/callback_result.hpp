// SPDX-License-Identifier: GPL-2.0-only

// 内核不同版本的 remove 回调可能是 void 或 int；trampoline 按镜像里成员的
// 真实返回类型做编译期适配，C++ 接口统一不关心返回值。

#pragma once

namespace linuxcpp {
namespace model {
namespace detail {

template <typename F>
struct function_result;

template <typename R, typename... Args>
struct function_result<R (*)(Args...)> {
	using type = R;
};

template <typename R>
struct zero_return {
	static R get() noexcept { return R{}; }
};

template <>
struct zero_return<void> {
	static void get() noexcept {}
};

}  // namespace detail
}  // namespace model
}  // namespace linuxcpp
