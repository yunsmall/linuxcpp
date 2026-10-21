// SPDX-License-Identifier: GPL-3.0-or-later

// 内核 mutex 的 RAII 封装，命名空间固定为 linuxcpp::std。

#pragma once

#include "bindings.hpp"

namespace linuxcpp {
namespace std {

// 实现在 linuxcpp_thunks.c；对象直接内嵌 struct mutex，不做堆分配
extern "C" {
void lc_mutex_init(linuxcpp::mutex *mutex);
void lc_mutex_destroy(linuxcpp::mutex *mutex);
void lc_mutex_lock(linuxcpp::mutex *mutex);
void lc_mutex_unlock(linuxcpp::mutex *mutex);
}

class mutex {
public:
	mutex() noexcept { lc_mutex_init(&handle_); }
	// 析构前必须保证没有线程持有或等待该锁；CONFIG_DEBUG_MUTEXES 下
	// mutex_destroy 会检查 owner，非空直接报 BUG
	~mutex() { lc_mutex_destroy(&handle_); }

	mutex(const mutex &) = delete;
	mutex &operator=(const mutex &) = delete;

	// 内嵌对象没有分配失败路径，保留 ok() 让现有调用方不用改
	bool ok() const noexcept { return true; }

	void lock() noexcept { lc_mutex_lock(&handle_); }
	void unlock() noexcept { lc_mutex_unlock(&handle_); }

private:
	linuxcpp::mutex handle_;
};

class lock_guard {
public:
	explicit lock_guard(mutex &m) noexcept : mutex_(m) { mutex_.lock(); }
	~lock_guard() { mutex_.unlock(); }

	lock_guard(const lock_guard &) = delete;
	lock_guard &operator=(const lock_guard &) = delete;

	bool ok() const noexcept { return true; }

private:
	mutex &mutex_;
};

}  // namespace std
}  // namespace linuxcpp
