// SPDX-License-Identifier: GPL-2.0-only

// misc 设备 + ioctl：C 风格 fops、用户态数据拷贝、标准库锁。

#include "linuxcpp.hpp"

using linuxcpp::iov_iter;
using linuxcpp::kiocb;
using linuxcpp::ssize_t;

namespace {

// _IOC 是函数宏，C++ 里用 constexpr 重写；位偏移来自内核头导出的常量
constexpr unsigned long ioc(unsigned long dir, unsigned long type,
			    unsigned long nr, unsigned long size)
{
	return (dir << linuxcpp::_IOC_DIRSHIFT) | (type << linuxcpp::_IOC_TYPESHIFT)
	     | (nr << linuxcpp::_IOC_NRSHIFT) | (size << linuxcpp::_IOC_SIZESHIFT);
}

constexpr unsigned long LC_SET_VALUE =
	ioc(linuxcpp::_IOC_WRITE, 'k', 1, sizeof(unsigned long));
constexpr unsigned long LC_GET_VALUE =
	ioc(linuxcpp::_IOC_READ, 'k', 2, sizeof(unsigned long));

unsigned long g_value;
linuxcpp::std::mutex *g_lock;

}  // namespace

static ssize_t demo_read(kiocb *iocb, iov_iter *to)
{
	static constexpr char message[] = "ioctl demo\n";
	const size_t length = sizeof(message) - 1;
	size_t pos = static_cast<size_t>(iocb->ki_pos);

	if (pos >= length)
		return 0;
	ssize_t n = static_cast<ssize_t>(
		linuxcpp::lc_copy_to_iter(message + pos, length - pos, to));
	// copy_to_iter 返回 0 而用户缓冲区还有空间，说明目标地址不可写，不能当 EOF
	if (n == 0 && to->count != 0)
		return -linuxcpp::EFAULT;
	iocb->ki_pos += n;
	return n;
}

static ssize_t demo_write(kiocb *iocb, iov_iter *from)
{
	char buffer[64];
	ssize_t n = static_cast<ssize_t>(
		linuxcpp::lc_copy_from_iter(buffer, sizeof(buffer), from));
	iocb->ki_pos += n;
	return n;
}

static long demo_ioctl(linuxcpp::file *file, unsigned int cmd, unsigned long arg)
{
	(void)file;
	linuxcpp::std::lock_guard guard(*g_lock);
	switch (cmd) {
	case LC_SET_VALUE:
		if (linuxcpp::lc_copy_from_user(&g_value,
						reinterpret_cast<const void *>(arg),
						sizeof(g_value)) != 0)
			return -linuxcpp::EFAULT;
		return 0;
	case LC_GET_VALUE:
		if (linuxcpp::lc_copy_to_user(reinterpret_cast<void *>(arg), &g_value,
					      sizeof(g_value)) != 0)
			return -linuxcpp::EFAULT;
		return 0;
	default:
		return -linuxcpp::ENOTTY;
	}
}

static const linuxcpp::file_operations demo_fops = {
	.owner = linuxcpp::this_module(),
	.read_iter = demo_read,
	.write_iter = demo_write,
	.unlocked_ioctl = demo_ioctl,
	.compat_ioctl = linuxcpp::compat_ptr_ioctl,
};

static linuxcpp::miscdevice demo_misc = {
	.minor = linuxcpp::MISC_DYNAMIC_MINOR,
	.name = LCPP_DEVICE_NAME,
	.fops = &demo_fops,
	.mode = LCPP_DEVICE_MODE,
};

static int demo_init(void)
{
	// 全局 C++ 对象的构造函数不会在内核模块加载时运行，锁必须显式 new
	g_lock = new linuxcpp::std::mutex();
	if (g_lock == nullptr || !g_lock->ok())
		return -linuxcpp::ENOMEM;
	int ret = linuxcpp::misc_register(&demo_misc);
	if (ret != 0) {
		delete g_lock;
		g_lock = nullptr;
	}
	return ret;
}

static void demo_exit(void)
{
	linuxcpp::misc_deregister(&demo_misc);
	delete g_lock;
	g_lock = nullptr;
}

LCPP_MODULE_RAW(demo_init, demo_exit)

// 对象宏由 module.toml 的 [bindings] macro 自动导出
static_assert(linuxcpp::MAY_READ != 0, "MAY_READ should be exported");
