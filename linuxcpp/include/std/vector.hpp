// SPDX-License-Identifier: GPL-3.0-or-later

// 内核态动态数组，命名空间固定为 linuxcpp::std。
// 扩容走 operator new(GFP_KERNEL)，只能在可睡眠上下文调用。

#pragma once

#include <stddef.h>

#include "../placement_new.hpp"

namespace linuxcpp {
namespace std {

// 没有 STL，动态数组自己实现；元素用 placement new 构造，析构时逐个销毁
template <typename T>
class vector {
public:
	vector() noexcept = default;
	// 元素用全局 operator new 分配，保证返回地址满足元素对齐
	static_assert(alignof(T) <= __STDCPP_DEFAULT_NEW_ALIGNMENT__,
		      "vector 元素的对齐超过 operator new 的默认对齐");

	~vector()
	{
		clear();
		::operator delete(data_);
	}

	vector(const vector &) = delete;
	vector &operator=(const vector &) = delete;

	// 移动只转移缓冲区，不搬元素；源对象随后处于空状态
	vector(vector &&other) noexcept
		: data_(other.data_), size_(other.size_), capacity_(other.capacity_)
	{
		other.data_ = nullptr;
		other.size_ = 0;
		other.capacity_ = 0;
	}

	vector &operator=(vector &&other) noexcept
	{
		if (this != &other) {
			clear();
			::operator delete(data_);
			data_ = other.data_;
			size_ = other.size_;
			capacity_ = other.capacity_;
			other.data_ = nullptr;
			other.size_ = 0;
			other.capacity_ = 0;
		}
		return *this;
	}

	using iterator = T *;
	using const_iterator = const T *;

	iterator begin() noexcept { return data_; }
	iterator end() noexcept { return data_ + size_; }
	const_iterator begin() const noexcept { return data_; }
	const_iterator end() const noexcept { return data_ + size_; }
	T *data() noexcept { return data_; }
	const T *data() const noexcept { return data_; }
	T &front() noexcept { return data_[0]; }
	const T &front() const noexcept { return data_[0]; }
	T &back() noexcept { return data_[size_ - 1]; }
	const T &back() const noexcept { return data_[size_ - 1]; }

	bool push_back(const T &value) { return append(value); }
	bool push_back(T &&value) { return append(static_cast<T &&>(value)); }

	template <typename... Args>
	bool emplace_back(Args &&...args)
	{
		if (size_ == capacity_ && !grow())
			return false;
		new (data_ + size_) T(static_cast<Args &&>(args)...);
		++size_;
		return true;
	}

	T &operator[](size_t index) noexcept { return data_[index]; }
	const T &operator[](size_t index) const noexcept { return data_[index]; }
	size_t size() const noexcept { return size_; }
	bool empty() const noexcept { return size_ == 0; }

	void clear()
	{
		while (size_ > 0)
			data_[--size_].~T();
	}

	void pop_back()
	{
		if (size_ > 0)
			data_[--size_].~T();
	}

private:
	template <typename U>
	bool append(U &&value)
	{
		if (size_ == capacity_ && !grow())
			return false;
		new (data_ + size_) T(static_cast<U &&>(value));
		++size_;
		return true;
	}

	bool grow()
	{
		if (capacity_ > static_cast<size_t>(-1) / 2)
			return false;
		size_t new_capacity = capacity_ ? capacity_ * 2 : 8;
		if (new_capacity > static_cast<size_t>(-1) / sizeof(T))
			return false;
		T *new_data = static_cast<T *>(::operator new(new_capacity * sizeof(T)));
		if (new_data == nullptr)
			return false;

		for (size_t i = 0; i < size_; ++i)
			new (new_data + i) T(static_cast<T &&>(data_[i]));
		for (size_t i = 0; i < size_; ++i)
			data_[i].~T();
		::operator delete(data_);

		data_ = new_data;
		capacity_ = new_capacity;
		return true;
	}

	T *data_ = nullptr;
	size_t size_ = 0;
	size_t capacity_ = 0;
};

}  // namespace std
}  // namespace linuxcpp
