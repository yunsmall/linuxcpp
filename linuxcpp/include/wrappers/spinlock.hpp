#pragma once
// module.toml:
// roots = ["spinlock_t"]
// thunk = ["spin_lock", "spin_unlock"]
// spin_lock_init 是宏，由 linuxcpp_thunks.c 手写提供
#include "bindings.hpp"

namespace linuxcpp {
namespace wrappers {

// spin_lock_init 是宏，由 linuxcpp_thunks.c 手写提供
extern "C" void lc_spin_lock_init(linuxcpp::spinlock_t *lock);

class spinlock {
public:
	spinlock() { lc_spin_lock_init(&lock_); }
	spinlock(const spinlock&) = delete;
	spinlock& operator=(const spinlock&) = delete;
	spinlock(spinlock&&) = delete;
	spinlock& operator=(spinlock&&) = delete;
	void lock() { lc_spin_lock(&lock_); }
	void unlock() { lc_spin_unlock(&lock_); }

private:
	linuxcpp::spinlock_t lock_;
};

class spin_guard {
public:
	explicit spin_guard(spinlock& lock) : lock_(lock) { lock_.lock(); }
	~spin_guard() { if (locked_) lock_.unlock(); }
	spin_guard(const spin_guard&) = delete;
	spin_guard& operator=(const spin_guard&) = delete;

	void dismiss() noexcept { locked_ = false; }

private:
	spinlock& lock_;
	bool locked_ = true;
};

} // namespace wrappers
} // namespace linuxcpp
