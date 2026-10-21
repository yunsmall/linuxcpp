// SPDX-License-Identifier: GPL-3.0-or-later

// 内核错误指针工具，对应 IS_ERR/PTR_ERR/ERR_PTR。

#pragma once

#include "bindings.hpp"

namespace linuxcpp {
namespace std {

// 内核错误指针的范围是 [-MAX_ERRNO, -1]，MAX_ERRNO 从内核头导出
template <typename T>
inline bool is_error(T *ptr)
{
	return reinterpret_cast<unsigned long>(ptr) >= static_cast<unsigned long>(-MAX_ERRNO);
}

template <typename T>
inline long ptr_error(T *ptr)
{
	return static_cast<long>(reinterpret_cast<unsigned long>(ptr));
}

template <typename T>
inline T *error_ptr(long error)
{
	return reinterpret_cast<T *>(static_cast<unsigned long>(error));
}

}  // namespace std
}  // namespace linuxcpp
