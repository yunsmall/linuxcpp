#pragma once
// kvec/iovec 纯字段包装，不调用内核函数。
#include <stddef.h>
#include "bindings.hpp"

namespace linuxcpp {
namespace wrappers {

class kvec {
public:
	kvec() {
		value.iov_base = nullptr;
		value.iov_len = 0;
	}

	kvec(void* base, size_t len) {
		value.iov_base = base;
		value.iov_len = len;
	}

	void* data() { return value.iov_base; }
	const void* data() const { return value.iov_base; }
	size_t size() const { return value.iov_len; }
	bool empty() const { return value.iov_len == 0; }

	linuxcpp::kvec value;
};

class iovec {
public:
	iovec() {
		value.iov_base = nullptr;
		value.iov_len = 0;
	}

	iovec(void* base, size_t len) {
		value.iov_base = base;
		value.iov_len = len;
	}

	void* data() { return value.iov_base; }
	const void* data() const { return value.iov_base; }
	size_t size() const { return value.iov_len; }
	bool empty() const { return value.iov_len == 0; }

	linuxcpp::iovec value;
};

} // namespace wrappers
} // namespace linuxcpp
