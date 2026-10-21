// SPDX-License-Identifier: GPL-3.0-or-later

// 可选的面向对象设备封装。
// C 风格模块只 include linuxcpp.hpp；需要继承 Device 或使用 misc_device 时再 include 这个头。

#pragma once

#include "linuxcpp.hpp"

namespace linuxcpp {

// 用户设备需要继承的基类；默认实现返回 -EINVAL
class Device {
public:
	virtual ~Device() = default;

	virtual int open(file *f)
	{
		(void)f;
		return 0;
	}

	virtual int release(file *f)
	{
		(void)f;
		return 0;
	}

	virtual ssize_t read(kiocb *iocb, iov_iter *to)
	{
		(void)iocb;
		(void)to;
		return -EINVAL;
	}

	virtual ssize_t write(kiocb *iocb, iov_iter *from)
	{
		(void)iocb;
		(void)from;
		return -EINVAL;
	}

	virtual long ioctl(file *f, unsigned int cmd, unsigned long arg)
	{
		(void)f;
		(void)cmd;
		(void)arg;
		return -ENOTTY;
	}
};

// 一个 misc 设备实例；fops/miscdevice 都内嵌在对象里，不依赖库级全局状态。
// 不同实例可以注册不同的 /dev 节点，回调按 file->f_op 反查所属对象。
class misc_device {
public:
	// 静态存储期默认构造只做常量初始化，不产生 .init_array 依赖
	constexpr misc_device() noexcept = default;
	misc_device(Device *dev, const char *name, int mode) noexcept
	{
		setup(dev, name, mode);
	}

	misc_device(const misc_device &) = delete;
	misc_device &operator=(const misc_device &) = delete;
	// 全局对象由 .fini_array 在模块 exit 后析构，这里兜底注销；stop 是幂等的
	~misc_device() { stop(); }

	void setup(Device *dev, const char *name, int mode) noexcept
	{
		// 已经注册时先注销，否则 registered_ 被清掉后旧 miscdevice 还挂在
		// misc_list 里，下次 start() 会重复注册同一个对象。
		// 有已打开 file 时不能调用：它们的 private_data 还指向旧 Device。
		if (registered_)
			stop();
		dev_ = dev;
		name_ = name;
		mode_ = mode;
		registered_ = false;
	}

	int start();
	// misc_deregister 不会等待已打开的 file；stop() 之后不要再释放 Device，
	// 否则 release/read 等回调会踩已释放对象。调用方负责串行化 start/stop。
	void stop();

	Device *device() const noexcept { return dev_; }
	bool registered() const noexcept { return registered_; }

	// 从 file->f_op 反查所属实例；fops_ 是对象成员，不需要全局状态
	static misc_device *from_fops(const file_operations *fops) noexcept;

private:
	Device *dev_ = nullptr;
	const char *name_ = nullptr;
	int mode_ = 0;
	bool registered_ = false;
	file_operations fops_{};
	miscdevice misc_{};
};

// from_fops 用 offsetof 从成员反查对象，标准布局是前提
static_assert(__is_standard_layout(misc_device), "misc_device 必须是标准布局");

}  // namespace linuxcpp
