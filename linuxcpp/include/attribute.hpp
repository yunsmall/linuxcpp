// SPDX-License-Identifier: GPL-2.0-only

// sysfs 属性和属性组。show/store 是普通虚函数，挂到设备上的时机由
// driver 的 probe/remove 决定，所以不放进构造函数。

#pragma once

#include "device_ref.hpp"

namespace linuxcpp {
namespace model {

class attribute {
public:
	attribute(const char *name, unsigned short mode) noexcept;
	virtual ~attribute() = default;

	attribute(const attribute &) = delete;
	attribute &operator=(const attribute &) = delete;

	virtual abi::ssize_t show(device &dev, char *buf, size_t size)
	{
		(void)dev;
		(void)buf;
		(void)size;
		return -abi::EINVAL;
	}

	virtual abi::ssize_t store(device &dev, const char *buf, size_t size)
	{
		(void)dev;
		(void)buf;
		(void)size;
		return -abi::EINVAL;
	}

	[[nodiscard]] int attach(device &dev) noexcept;
	void detach(device &dev) noexcept;
	abi::device_attribute *kernel() noexcept { return &holder_.attr; }

private:
	struct holder {
		abi::device_attribute attr{};
		attribute *owner = nullptr;
	};

	static holder *from_attr(abi::device_attribute *attr) noexcept;
	static abi::ssize_t show_trampoline(abi::device *dev,
				       abi::device_attribute *attr,
				       char *buf) noexcept;
	static abi::ssize_t store_trampoline(abi::device *dev,
					abi::device_attribute *attr,
					const char *buf, size_t count) noexcept;

	holder holder_{};
};

class attribute_group {
public:
	static constexpr unsigned kMaxAttributes = 16;

	explicit attribute_group(const char *name = nullptr) noexcept;
	attribute_group(const attribute_group &) = delete;
	attribute_group &operator=(const attribute_group &) = delete;

	bool add(attribute &attr) noexcept;
	[[nodiscard]] int attach(device &dev) noexcept;
	void detach(device &dev) noexcept;
	abi::attribute_group *kernel() noexcept { return &group_; }

private:
	abi::attribute_group group_{};
	abi::attribute *attrs_[kMaxAttributes + 1]{};
	unsigned count_ = 0;
};

inline attribute::attribute(const char *name, unsigned short mode) noexcept
{
	holder_.owner = this;
	holder_.attr = {};
	holder_.attr.attr.name = name;
	holder_.attr.attr.mode = mode;
	holder_.attr.show = &show_trampoline;
	holder_.attr.store = &store_trampoline;
}

inline attribute::holder *
attribute::from_attr(abi::device_attribute *attr) noexcept
{
	return reinterpret_cast<holder *>(
		reinterpret_cast<char *>(attr) - offsetof(holder, attr));
}

inline abi::ssize_t attribute::show_trampoline(abi::device *dev,
					  abi::device_attribute *attr,
					  char *buf) noexcept
{
	holder *h = from_attr(attr);

	if (!h || !h->owner)
		return -abi::EINVAL;
	device_ref ref(dev);
	// sysfs 的 show 缓冲区按 PAGE_SIZE 约定
	return h->owner->show(ref, buf, abi::PAGE_SIZE);
}

inline abi::ssize_t attribute::store_trampoline(abi::device *dev,
					   abi::device_attribute *attr,
					   const char *buf,
					   size_t count) noexcept
{
	holder *h = from_attr(attr);

	if (!h || !h->owner)
		return -abi::EINVAL;
	device_ref ref(dev);
	return h->owner->store(ref, buf, count);
}

inline int attribute::attach(device &dev) noexcept
{
	if (!dev.kernel() || !holder_.attr.attr.name)
		return -abi::EINVAL;
	return abi::device_create_file(dev.kernel(), &holder_.attr);
}

inline void attribute::detach(device &dev) noexcept
{
	if (dev.kernel())
		abi::device_remove_file(dev.kernel(), &holder_.attr);
}

inline attribute_group::attribute_group(const char *name) noexcept
{
	group_ = {};
	group_.name = name;
	attrs_[0] = nullptr;
	group_.attrs = attrs_;
}

inline bool attribute_group::add(attribute &attr) noexcept
{
	if (count_ >= kMaxAttributes)
		return false;
	attrs_[count_++] = &attr.kernel()->attr;
	attrs_[count_] = nullptr;
	return true;
}

inline int attribute_group::attach(device &dev) noexcept
{
	if (!dev.kernel())
		return -abi::EINVAL;
	return abi::sysfs_create_group(&dev.kernel()->kobj, &group_);
}

inline void attribute_group::detach(device &dev) noexcept
{
	if (dev.kernel())
		abi::sysfs_remove_group(&dev.kernel()->kobj, &group_);
}

}  // namespace model
}  // namespace linuxcpp
