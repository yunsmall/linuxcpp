#pragma once
// module.toml:
// roots = ["atomic_t"]
// 不需要配置 thunk：atomic 操作由 linuxcpp_thunks.c 手写提供
#include "bindings.hpp"

namespace linuxcpp {
namespace wrappers {

extern "C" {
int lc_atomic_read(const linuxcpp::atomic_t *value);
void lc_atomic_set(linuxcpp::atomic_t *value, int v);
void lc_atomic_add(int v, linuxcpp::atomic_t *value);
void lc_atomic_sub(int v, linuxcpp::atomic_t *value);
void lc_atomic_inc(linuxcpp::atomic_t *value);
void lc_atomic_dec(linuxcpp::atomic_t *value);
}

class atomic {
public:
	atomic() { lc_atomic_set(&value_, 0); }
	atomic(const atomic&) = delete;
	atomic& operator=(const atomic&) = delete;
	atomic(atomic&&) = delete;
	atomic& operator=(atomic&&) = delete;
	int get() const { return lc_atomic_read(&value_); }
	void set(int v) { lc_atomic_set(&value_, v); }
	void add(int v) { lc_atomic_add(v, &value_); }
	void sub(int v) { lc_atomic_sub(v, &value_); }
	void inc() { lc_atomic_inc(&value_); }
	void dec() { lc_atomic_dec(&value_); }

private:
	linuxcpp::atomic_t value_;
};

} // namespace wrappers
} // namespace linuxcpp
