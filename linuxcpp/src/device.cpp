// SPDX-License-Identifier: GPL-3.0-or-later

// Device 对象风格和 misc 设备注册的实现。
// 所有状态都在 misc_device 实例里，不使用库级全局变量。

#include <stddef.h>

#include "device.hpp"

namespace linuxcpp {

misc_device *misc_device::from_fops(const file_operations *fops) noexcept
{
	if (fops == nullptr)
		return nullptr;
	return reinterpret_cast<misc_device *>(
		reinterpret_cast<char *>(const_cast<file_operations *>(fops))
		- offsetof(misc_device, fops_));
}

int misc_device::start()
{
	// 同一个实例只注册一次；不同实例各自维护自己的 fops/miscdevice
	if (registered_)
		return -EBUSY;
	if (dev_ == nullptr)
		return -EINVAL;

	fops_ = {};
	fops_.owner = this_module();
	fops_.open = [](inode *inode, file *f) -> int {
		(void)inode;
		misc_device *self = misc_device::from_fops(f->f_op);
		if (self == nullptr || self->dev_ == nullptr)
			return -ENODEV;
		// open 失败时 VFS 不会置 FMODE_OPENED，也不会调用 release，
		// 所以 private_data 不需要在这里清空
		f->private_data = self->dev_;
		return self->dev_->open(f);
	};
	fops_.release = [](inode *inode, file *f) -> int {
		(void)inode;
		Device *dev = static_cast<Device *>(f->private_data);
		return dev != nullptr ? dev->release(f) : -ENODEV;
	};
	fops_.read_iter = [](kiocb *iocb, iov_iter *to) -> ssize_t {
		file *f = iocb->ki_filp;
		Device *dev = f != nullptr ? static_cast<Device *>(f->private_data) : nullptr;
		return dev != nullptr ? dev->read(iocb, to) : -ENODEV;
	};
	fops_.write_iter = [](kiocb *iocb, iov_iter *from) -> ssize_t {
		file *f = iocb->ki_filp;
		Device *dev = f != nullptr ? static_cast<Device *>(f->private_data) : nullptr;
		return dev != nullptr ? dev->write(iocb, from) : -ENODEV;
	};
	fops_.unlocked_ioctl = [](file *f, unsigned int cmd, unsigned long arg) -> long {
		Device *dev = static_cast<Device *>(f->private_data);
		return dev != nullptr ? dev->ioctl(f, cmd, arg) : -ENODEV;
	};
	fops_.compat_ioctl = compat_ptr_ioctl;

	misc_ = {};
	misc_.minor = MISC_DYNAMIC_MINOR;
	misc_.name = name_;
	misc_.fops = &fops_;
	misc_.mode = static_cast<decltype(misc_.mode)>(mode_);

	int ret = misc_register(&misc_);
	if (ret != 0)
		return ret;
	registered_ = true;
	return 0;
}

void misc_device::stop()
{
	if (!registered_)
		return;
	misc_deregister(&misc_);
	registered_ = false;
}

}  // namespace linuxcpp
