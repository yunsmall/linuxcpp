// SPDX-License-Identifier: GPL-2.0-only

// 非拥有设备句柄。内核驱动回调拿到 struct device * 时用它包一层，
// 不负责生命周期，也不能被释放。

#pragma once

#include "device.hpp"

namespace linuxcpp {
namespace model {

class device_ref final : public device {
public:
	constexpr device_ref() noexcept = default;
	constexpr explicit device_ref(abi::device *ptr) noexcept : ptr_(ptr) {}

	abi::device *kernel() override { return ptr_; }

	const char *name() const override
	{
		if (!ptr_)
			return nullptr;
		return ptr_->kobj.name ? ptr_->kobj.name : ptr_->init_name;
	}

	void *drvdata() const noexcept
	{
		return ptr_ ? ptr_->driver_data : nullptr;
	}

	void set_drvdata(void *data) noexcept
	{
		if (ptr_)
			ptr_->driver_data = data;
	}

	template <typename T>
	T *drvdata_as() const noexcept
	{
		return static_cast<T *>(drvdata());
	}

	explicit operator bool() const noexcept { return ptr_ != nullptr; }
	abi::device *get() const noexcept { return ptr_; }
	abi::device *operator->() const noexcept { return ptr_; }

private:
	abi::device *ptr_ = nullptr;
};

}  // namespace model
}  // namespace linuxcpp
