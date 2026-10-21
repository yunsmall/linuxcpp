// SPDX-License-Identifier: GPL-3.0-or-later

// 最小示例：像写 C 模块一样直接填 file_operations。

#include "linuxcpp.hpp"

using linuxcpp::iov_iter;
using linuxcpp::kiocb;
using linuxcpp::ssize_t;

static ssize_t hello_read(kiocb *iocb, iov_iter *to)
{
	// 返回本次消费的字节数即可，内核会据此推进 ki_pos；小缓冲区分多次 read
	// 时必须从上次的位置继续，不能一次没读完就返回 EOF
	static constexpr char message[] = "hello from cpp\n";
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

static ssize_t hello_write(kiocb *iocb, iov_iter *from)
{
	char buffer[64];
	ssize_t n = static_cast<ssize_t>(
		linuxcpp::lc_copy_from_iter(buffer, sizeof(buffer), from));
	iocb->ki_pos += n;
	return n;
}

static const linuxcpp::file_operations hello_fops = {
	.owner = linuxcpp::this_module(),
	.read_iter = hello_read,
	.write_iter = hello_write,
};

static linuxcpp::miscdevice hello_misc = {
	.minor = linuxcpp::MISC_DYNAMIC_MINOR,
	.name = LCPP_DEVICE_NAME,
	.fops = &hello_fops,
	.mode = LCPP_DEVICE_MODE,
};

static int hello_init(void)
{
	// 变参 printk 由核心库的 C thunk 转发，用法和内核里一致
	linuxcpp::printk("hello_misc: init\n");
	return linuxcpp::misc_register(&hello_misc);
}

static void hello_exit(void)
{
	linuxcpp::printk("hello_misc: exit\n");
	linuxcpp::misc_deregister(&hello_misc);
}

LCPP_MODULE_RAW(hello_init, hello_exit)
