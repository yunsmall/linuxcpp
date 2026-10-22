// SPDX-License-Identifier: GPL-2.0-only

// 不使用 libc++，只使用 linuxcpp 的 C 库子集。启动时实际调用
// malloc/calloc/realloc/free、qsort、bsearch、strtol、snprintf、printf 和 time。

#include "linuxcpp.hpp"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

using linuxcpp::iov_iter;
using linuxcpp::kiocb;
using linuxcpp::ssize_t;

namespace {

char g_message[256];

int compare_int(const void *a, const void *b)
{
	int left = *static_cast<const int *>(a);
	int right = *static_cast<const int *>(b);

	return (left > right) - (left < right);
}

ssize_t demo_read(kiocb *iocb, iov_iter *to)
{
	const size_t length = strlen(g_message);
	size_t pos = static_cast<size_t>(iocb->ki_pos);

	if (pos >= length)
		return 0;
	ssize_t n = static_cast<ssize_t>(
		linuxcpp::lc_copy_to_iter(g_message + pos, length - pos, to));
	if (n == 0 && to->count != 0)
		return -linuxcpp::EFAULT;
	iocb->ki_pos += n;
	return n;
}

const linuxcpp::file_operations demo_fops = {
	.owner = linuxcpp::this_module(),
	.read_iter = demo_read,
};

linuxcpp::miscdevice demo_misc = {
	.minor = linuxcpp::MISC_DYNAMIC_MINOR,
	.name = LCPP_DEVICE_NAME,
	.fops = &demo_fops,
	.mode = LCPP_DEVICE_MODE,
};

int demo_init(void)
{
	int *values = static_cast<int *>(malloc(6 * sizeof(int)));
	int *zeros = static_cast<int *>(calloc(3, sizeof(int)));
	int *grown = nullptr;
	char *end = nullptr;
	time_t now;
	long parsed;
	int result;

	if (!values || !zeros) {
		free(values);
		free(zeros);
		return -linuxcpp::ENOMEM;
	}

	values[0] = 5;
	values[1] = 1;
	values[2] = 4;
	values[3] = 2;
	values[4] = 6;
	values[5] = 3;
	qsort(values, 6, sizeof(int), compare_int);

	grown = static_cast<int *>(realloc(values, 8 * sizeof(int)));
	if (!grown) {
		free(values);
		free(zeros);
		return -linuxcpp::ENOMEM;
	}
	values = grown;

	int key = 3;
	int *found = static_cast<int *>(
		bsearch(&key, values, 6, sizeof(int), compare_int));

	errno = 0;
	parsed = strtol("12345xyz", &end, 10);
	now = time(nullptr);

	result = snprintf(g_message, sizeof(g_message),
		"libc: sorted=%d,%d,%d,%d,%d,%d found=%d calloc=%d,%d,%d "
		"strtol=%ld rest=%s errno=%d time_ok=%d strerror=%s\n",
		values[0], values[1], values[2], values[3], values[4], values[5],
		found ? *found : -1,
		zeros[0], zeros[1], zeros[2],
		parsed, end ? end : "?", errno, now > 0,
		strerror(EINVAL));

	free(values);
	free(zeros);
	if (result < 0)
		return -linuxcpp::EINVAL;

	printf("libc_demo: printf through vprintk\n");
	return linuxcpp::misc_register(&demo_misc);
}

void demo_exit(void)
{
	linuxcpp::misc_deregister(&demo_misc);
}

}  // namespace

LCPP_MODULE_RAW(demo_init, demo_exit)
