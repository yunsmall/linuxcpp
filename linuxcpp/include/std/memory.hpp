// SPDX-License-Identifier: GPL-2.0-only

// 内核态内存设施，命名空间固定为 linuxcpp::std。
// 分配最终走 lc_kmalloc(GFP_KERNEL)，只能在可睡眠上下文使用；
// 自旋锁内/中断上下文不能调用 unique_ptr、vector 等会分配的对象。

#pragma once

#include <stddef.h>

namespace linuxcpp {
namespace std {

// 独占所有权指针，析构时 delete（最终走内核的 kmalloc/kfree）
template <typename T>
class unique_ptr {
public:
	unique_ptr() noexcept = default;
	explicit unique_ptr(T *ptr) noexcept : ptr_(ptr) {}
	~unique_ptr() { delete ptr_; }

	unique_ptr(const unique_ptr &) = delete;
	unique_ptr &operator=(const unique_ptr &) = delete;
	unique_ptr(unique_ptr &&other) noexcept : ptr_(other.release()) {}
	unique_ptr &operator=(unique_ptr &&other) noexcept
	{
		reset(other.release());
		return *this;
	}

	T *get() const noexcept { return ptr_; }
	T *operator->() const noexcept { return ptr_; }
	T &operator*() const noexcept { return *ptr_; }
	explicit operator bool() const noexcept { return ptr_ != nullptr; }

	T *release() noexcept
	{
		T *ptr = ptr_;
		ptr_ = nullptr;
		return ptr;
	}

	void reset(T *ptr = nullptr) noexcept
	{
		if (ptr_ != ptr) {
			delete ptr_;
			ptr_ = ptr;
		}
	}

private:
	T *ptr_ = nullptr;
};

// 数组版本必须用 delete[]，不能复用 delete ptr_
template <typename T>
class unique_ptr<T[]> {
public:
	unique_ptr() noexcept = default;
	explicit unique_ptr(T *ptr) noexcept : ptr_(ptr) {}
	~unique_ptr() { delete[] ptr_; }

	unique_ptr(const unique_ptr &) = delete;
	unique_ptr &operator=(const unique_ptr &) = delete;
	unique_ptr(unique_ptr &&other) noexcept : ptr_(other.release()) {}
	unique_ptr &operator=(unique_ptr &&other) noexcept
	{
		reset(other.release());
		return *this;
	}

	T *get() const noexcept { return ptr_; }
	T &operator[](size_t index) const noexcept { return ptr_[index]; }
	explicit operator bool() const noexcept { return ptr_ != nullptr; }

	T *release() noexcept
	{
		T *ptr = ptr_;
		ptr_ = nullptr;
		return ptr;
	}

	void reset(T *ptr = nullptr) noexcept
	{
		if (ptr_ != ptr) {
			delete[] ptr_;
			ptr_ = ptr;
		}
	}

private:
	T *ptr_ = nullptr;
};

}  // namespace std
}  // namespace linuxcpp
