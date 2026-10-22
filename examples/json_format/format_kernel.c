// SPDX-License-Identifier: GPL-2.0-only

// fd 的读取和原地回写。这个翻译单元只 include 内核头；
// JSON 解析和格式化在 format_json.cpp 里，通过纯 C 接口调用。

#include "json_format.h"

#include <linux/errno.h>
#include <linux/file.h>
#include <linux/fs.h>
#include <linux/kernel.h>
#include <linux/printk.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/types.h>

#define JSON_MAX_INPUT (1024U * 1024U)
#define JSON_MAX_OUTPUT (4U * 1024U * 1024U)

int lc_format_json_fd(int fd);

static int read_file(struct file *file, char *buffer, size_t size)
{
	loff_t pos = 0;

	while (pos < (loff_t)size) {
		ssize_t n = kernel_read(file, buffer + pos, size - (size_t)pos,
					&pos);

		if (n < 0)
			return (int)n;
		if (n == 0)
			return -EIO;
	}
	return 0;
}

static int write_file(struct file *file, const char *buffer, size_t size)
{
	loff_t pos = 0;

	while (pos < (loff_t)size) {
		ssize_t n = kernel_write(file, buffer + pos,
					 size - (size_t)pos, &pos);

		if (n < 0)
			return (int)n;
		if (n == 0)
			return -EIO;
	}
	return 0;
}

int lc_format_json_fd(int fd)
{
	struct fd f = fdget(fd);
	struct file *file;
	struct inode *inode;
	char *input = NULL;
	char *output = NULL;
	loff_t file_size;
	size_t size;
	long formatted_length;
	int ret = 0;

	if (fd_empty(f))
		return -EBADF;

	file = fd_file(f);
	inode = file_inode(file);
	if (!S_ISREG(inode->i_mode)) {
		ret = -EINVAL;
		goto out_fd;
	}
	if (!(file->f_mode & FMODE_READ) ||
	    !(file->f_mode & FMODE_WRITE)) {
		ret = -EACCES;
		goto out_fd;
	}
	if (IS_APPEND(inode)) {
		ret = -EPERM;
		goto out_fd;
	}

	file_size = i_size_read(inode);
	if (file_size <= 0) {
		ret = -EINVAL;
		goto out_fd;
	}
	if (file_size > (loff_t)JSON_MAX_INPUT) {
		ret = -EFBIG;
		goto out_fd;
	}
	size = (size_t)file_size;

	input = kmalloc(size + 1, GFP_KERNEL);
	if (!input) {
		ret = -ENOMEM;
		goto out_fd;
	}

	ret = read_file(file, input, size);
	if (ret)
		goto out;
	input[size] = '\0';

	formatted_length = lc_pretty_json(input, (unsigned long)size, NULL, 0);
	if (formatted_length < 0) {
		pr_err("json_format: invalid JSON\n");
		ret = (int)formatted_length;
		goto out;
	}
	if (formatted_length > (long)JSON_MAX_OUTPUT) {
		ret = -EFBIG;
		goto out;
	}

	// 输出比原文短时补空格，文件大小保持不变，不需要 truncate
	size_t write_length = (size_t)formatted_length > size
				      ? (size_t)formatted_length
				      : size;

	output = kmalloc(write_length + 1, GFP_KERNEL);
	if (!output) {
		ret = -ENOMEM;
		goto out;
	}

	if (lc_pretty_json(input, (unsigned long)size, output,
			   (unsigned long)(write_length + 1)) !=
	    formatted_length) {
		ret = -EIO;
		goto out;
	}
	if ((size_t)formatted_length < size)
		memset(output + formatted_length, ' ',
		       size - (size_t)formatted_length);

	ret = write_file(file, output, write_length);

out:
	kfree(output);
	kfree(input);
out_fd:
	fdput(f);
	return ret;
}
