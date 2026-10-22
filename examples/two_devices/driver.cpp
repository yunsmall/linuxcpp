// SPDX-License-Identifier: GPL-2.0-only

// 一个模块注册两个 misc 设备，演示 C 风格下没有单例限制。

#include "linuxcpp.hpp"

using linuxcpp::iov_iter;
using linuxcpp::kiocb;
using linuxcpp::ssize_t;

static ssize_t a_read(kiocb *iocb, iov_iter *to)
{
	static constexpr char message[] = "device a\n";
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

static ssize_t b_read(kiocb *iocb, iov_iter *to)
{
	static constexpr char message[] = "device b\n";
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

static const linuxcpp::file_operations a_fops = {
	.owner = linuxcpp::this_module(),
	.read_iter = a_read,
};

static const linuxcpp::file_operations b_fops = {
	.owner = linuxcpp::this_module(),
	.read_iter = b_read,
};

static linuxcpp::miscdevice a_misc = {
	.minor = linuxcpp::MISC_DYNAMIC_MINOR,
	.name = "two_a",
	.fops = &a_fops,
	.mode = 0666,
};

static linuxcpp::miscdevice b_misc = {
	.minor = linuxcpp::MISC_DYNAMIC_MINOR,
	.name = "two_b",
	.fops = &b_fops,
	.mode = 0666,
};

static int two_init(void)
{
	int ret = linuxcpp::misc_register(&a_misc);
	if (ret != 0)
		return ret;
	ret = linuxcpp::misc_register(&b_misc);
	if (ret != 0) {
		linuxcpp::misc_deregister(&a_misc);
		return ret;
	}
	return 0;
}

static void two_exit(void)
{
	linuxcpp::misc_deregister(&b_misc);
	linuxcpp::misc_deregister(&a_misc);
}

LCPP_MODULE_RAW(two_init, two_exit)
