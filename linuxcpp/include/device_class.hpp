// SPDX-License-Identifier: GPL-2.0-only

// struct class 的 C++ 封装：构造注册、析构注销。

#pragma once

#include "linuxcpp.hpp"

namespace linuxcpp {
namespace model {

class device_class {
public:
	explicit device_class(const char *name) noexcept
	{
		cls_.name = name;
		error_ = name ? abi::class_register(&cls_) : -abi::EINVAL;
	}

	~device_class()
	{
		if (error_ == 0) {
			error_ = -abi::EINVAL;
			abi::class_unregister(&cls_);
		}
	}

	device_class(const device_class &) = delete;
	device_class &operator=(const device_class &) = delete;
	device_class(device_class &&) = delete;
	device_class &operator=(device_class &&) = delete;

	[[nodiscard]] int error() const noexcept { return error_; }
	explicit operator bool() const noexcept { return error_ == 0; }
	abi::class_ *kernel() noexcept { return &cls_; }

private:
	abi::class_ cls_{};
	int error_ = -abi::EINVAL;
};

}  // namespace model
}  // namespace linuxcpp
