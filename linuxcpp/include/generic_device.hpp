// SPDX-License-Identifier: GPL-2.0-only

// 挂在自定义 bus 上的通用 struct device。构造注册、析构注销；
// 需要文件操作时用 misc_device<D>/char_device<D>，不要在这里重复实现 fops。

#pragma once

#include "attribute.hpp"
#include "bus.hpp"
#include "device.hpp"

namespace linuxcpp {
namespace model {

class generic_device : public device {
public:
	generic_device(const char *name, bus &bus, device *parent = nullptr,
		       void *drvdata = nullptr) noexcept;
	~generic_device() override;

	generic_device(const generic_device &) = delete;
	generic_device &operator=(const generic_device &) = delete;
	generic_device(generic_device &&) = delete;
	generic_device &operator=(generic_device &&) = delete;

	abi::device *kernel() override { return &holder_.dev; }
	const char *name() const override
	{
		return holder_.dev.kobj.name ? holder_.dev.kobj.name
					     : holder_.dev.init_name;
	}

	void *drvdata() const noexcept { return holder_.dev.driver_data; }
	void set_drvdata(void *data) noexcept { holder_.dev.driver_data = data; }

	[[nodiscard]] int error() const noexcept { return error_; }
	explicit operator bool() const noexcept { return error_ == 0; }

	[[nodiscard]] int create_file(attribute &attr) noexcept
	{
		return attr.attach(*this);
	}

	void remove_file(attribute &attr) noexcept { attr.detach(*this); }

	[[nodiscard]] int create_group(attribute_group &group) noexcept
	{
		return group.attach(*this);
	}

	void remove_group(attribute_group &group) noexcept
	{
		group.detach(*this);
	}

private:
	struct holder {
		abi::device dev{};
		generic_device *owner = nullptr;
	};

	static holder *from_device(abi::device *dev) noexcept;
	static void release_trampoline(abi::device *dev) noexcept;

	holder holder_{};
	int error_ = -abi::EINVAL;
};

inline generic_device::generic_device(const char *name, bus &bus,
				      device *parent, void *drvdata) noexcept
{
	holder_.owner = this;
	holder_.dev = {};
	holder_.dev.init_name = name;
	holder_.dev.bus = bus.kernel();
	holder_.dev.parent = parent ? parent->kernel() : nullptr;
	holder_.dev.driver_data = drvdata;
	holder_.dev.release = &release_trampoline;
	error_ = name ? abi::device_register(&holder_.dev) : -abi::EINVAL;
}

inline generic_device::~generic_device()
{
	if (error_ == 0) {
		error_ = -abi::EINVAL;
		abi::device_unregister(&holder_.dev);
	}
}

inline generic_device::holder *
generic_device::from_device(abi::device *dev) noexcept
{
	return reinterpret_cast<holder *>(
		reinterpret_cast<char *>(dev) - offsetof(holder, dev));
}

inline void generic_device::release_trampoline(abi::device *dev) noexcept
{
	holder *h = from_device(dev);

	if (h && h->owner)
		h->owner->on_release();
}

}  // namespace model
}  // namespace linuxcpp
