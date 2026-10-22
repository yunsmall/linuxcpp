// SPDX-License-Identifier: GPL-2.0-only

// 设备基类、字符设备和 misc 设备。
//
// 内核的 struct device 用嵌入实现继承，file_operations 用函数指针实现虚表。
// 这里把这两层翻成 C++：device 是基类，char_device 的虚函数就是 file_operations，
// misc_device 再负责把它注册成 /dev 节点。设备模型的 bus/driver/platform 在
// device_model.hpp 里，不塞进同一个文件。
//
// char_device 用 CRTP 拿到派生类类型：派生类覆盖了哪个文件操作，就只给对应的
// file_operations 指针装 trampoline，没覆盖的保持 NULL，交给 VFS 默认语义。

#pragma once

#include <stddef.h>

#include "linuxcpp.hpp"

namespace linuxcpp {
namespace model {

namespace detail {

// 派生类覆盖虚函数后，&Derived::method 的类型会从“指向基类成员”变成
// “指向派生类成员”；不需要 RTTI，也不需要 C++26 反射
template <typename A, typename B>
struct same_type {
	static constexpr bool value = false;
};

template <typename A>
struct same_type<A, A> {
	static constexpr bool value = true;
};

}  // namespace detail

class device {
public:
	virtual ~device() = default;

	// 内核里的 struct device；没有对应内核对象时返回 nullptr
	virtual abi::device *kernel() = 0;
	virtual const char *name() const = 0;

	// struct device.release 的 C++ 版本
	virtual void on_release() {}
};

// 字符设备基类：这些虚函数就是 file_operations。
// Derived 是最终设备类型，用来判断哪些虚函数被覆盖。
template <typename Derived>
class char_device : public device {
public:
	virtual ~char_device() = default;

	char_device(const char_device &) = delete;
	char_device &operator=(const char_device &) = delete;
	char_device(char_device &&) = delete;
	char_device &operator=(char_device &&) = delete;

	virtual int open(abi::file *f)
	{
		(void)f;
		return 0;
	}

	virtual int release(abi::file *f)
	{
		(void)f;
		return 0;
	}

	virtual abi::ssize_t read(abi::kiocb *iocb, abi::iov_iter *to)
	{
		(void)iocb;
		(void)to;
		return -abi::EINVAL;
	}

	virtual abi::ssize_t write(abi::kiocb *iocb, abi::iov_iter *from)
	{
		(void)iocb;
		(void)from;
		return -abi::EINVAL;
	}

	virtual long ioctl(abi::file *f, unsigned int cmd, unsigned long arg)
	{
		(void)f;
		(void)cmd;
		(void)arg;
		return -abi::ENOTTY;
	}

protected:
	char_device() noexcept
	{
		fops_holder_.owner = this;
		fops_holder_.fops = {};

		abi::file_operations &fops = fops_holder_.fops;

		fops.owner = this_module();
		// open 必须始终安装：它负责把对象指针放进 file->private_data，
		// 后面的 read/write/ioctl 才能找回对象
		fops.open = &open_trampoline;
		fops.release = &release_trampoline;
		if constexpr (has_read)
			fops.read_iter = &read_trampoline;
		if constexpr (has_write)
			fops.write_iter = &write_trampoline;
		if constexpr (has_ioctl) {
			fops.unlocked_ioctl = &ioctl_trampoline;
			fops.compat_ioctl = abi::compat_ptr_ioctl;
		}
	}

	// 多态对象不能拿来做 offsetof；这个标准布局 holder 只存内核结构和
	// owner 指针，trampoline 从 file_operations 反查回 char_device
	struct holder {
		abi::file_operations fops{};
		char_device *owner = nullptr;
	};

	holder fops_holder_{};

private:
	// 派生类覆盖虚函数后，成员指针的类型会变成 Derived::*。
	// 这些方法必须是 public，且不能对同名 fops 方法加重载
	static constexpr bool has_read =
		!detail::same_type<decltype(&Derived::read),
				   decltype(&char_device::read)>::value;
	static constexpr bool has_write =
		!detail::same_type<decltype(&Derived::write),
				   decltype(&char_device::write)>::value;
	static constexpr bool has_ioctl =
		!detail::same_type<decltype(&Derived::ioctl),
				   decltype(&char_device::ioctl)>::value;

	static holder *from_fops(const abi::file_operations *fops) noexcept
	{
		if (!fops)
			return nullptr;
		return reinterpret_cast<holder *>(
			reinterpret_cast<char *>(
				const_cast<abi::file_operations *>(fops)) -
			offsetof(holder, fops));
	}

	static int open_trampoline(abi::inode *inode, abi::file *file) noexcept
	{
		(void)inode;
		holder *h = from_fops(file->f_op);

		if (!h || !h->owner)
			return -abi::ENODEV;
		// open 失败时 VFS 不会置 FMODE_OPENED，也不会调用 release
		file->private_data = h->owner;
		return h->owner->open(file);
	}

	static int release_trampoline(abi::inode *inode, abi::file *file) noexcept
	{
		(void)inode;
		auto *self = static_cast<char_device *>(file->private_data);

		return self ? self->release(file) : -abi::ENODEV;
	}

	static abi::ssize_t read_trampoline(abi::kiocb *iocb,
					    abi::iov_iter *to) noexcept
	{
		abi::file *file = iocb->ki_filp;
		auto *self = file ? static_cast<char_device *>(file->private_data)
				  : nullptr;

		return self ? self->read(iocb, to) : -abi::ENODEV;
	}

	static abi::ssize_t write_trampoline(abi::kiocb *iocb,
					     abi::iov_iter *from) noexcept
	{
		abi::file *file = iocb->ki_filp;
		auto *self = file ? static_cast<char_device *>(file->private_data)
				  : nullptr;

		return self ? self->write(iocb, from) : -abi::ENODEV;
	}

	static long ioctl_trampoline(abi::file *file, unsigned int cmd,
				     unsigned long arg) noexcept
	{
		auto *self = static_cast<char_device *>(file->private_data);

		return self ? self->ioctl(file, cmd, arg) : -abi::ENODEV;
	}
};

// misc 设备：构造注册、析构注销；用户继承它并覆盖文件操作虚函数
template <typename Derived>
class misc_device : public char_device<Derived> {
public:
	explicit misc_device(const char *name, int mode = 0666) noexcept
	{
		misc_.minor = abi::MISC_DYNAMIC_MINOR;
		misc_.name = name;
		misc_.fops = &this->fops_holder_.fops;
		misc_.mode = static_cast<decltype(misc_.mode)>(mode);
		error_ = abi::misc_register(&misc_);
	}

	~misc_device() override
	{
		if (error_ == 0) {
			error_ = -abi::EINVAL;
			abi::misc_deregister(&misc_);
		}
	}

	misc_device(const misc_device &) = delete;
	misc_device &operator=(const misc_device &) = delete;
	misc_device(misc_device &&) = delete;
	misc_device &operator=(misc_device &&) = delete;

	abi::device *kernel() override { return misc_.this_device; }
	const char *name() const override { return misc_.name; }

	[[nodiscard]] int error() const noexcept { return error_; }
	explicit operator bool() const noexcept { return error_ == 0; }

private:
	abi::miscdevice misc_{};
	int error_ = -abi::EINVAL;
};

}  // namespace model
}  // namespace linuxcpp
