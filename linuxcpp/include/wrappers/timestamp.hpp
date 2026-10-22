#pragma once
// 时间戳包装，仅做字段运算，不调用内核函数。
#include "bindings.hpp"

namespace linuxcpp {
namespace wrappers {

class timestamp {
public:
	timestamp() {
		ts_.tv_sec = 0;
		ts_.tv_nsec = 0;
	}

	timestamp(long long sec, long long nsec = 0) {
		// 32 位平台上 tv_nsec 是 long，必须先在 long long 里规范化再写入，
		// 否则超过 LONG_MAX 的 nsec 会被截断成负数
		normalize_values(sec, nsec);
		ts_.tv_sec = sec;
		ts_.tv_nsec = static_cast<long>(nsec);
	}

	long long to_ns() const {
		return static_cast<long long>(ts_.tv_sec) * NS_PER_SEC + static_cast<long long>(ts_.tv_nsec);
	}

	static timestamp from_ns(long long ns) {
		timestamp t;
		t.ts_.tv_sec = ns / NS_PER_SEC;
		t.ts_.tv_nsec = static_cast<long>(ns % NS_PER_SEC);
		t.normalize();
		return t;
	}

	static void normalize_values(long long &sec, long long &nsec) {
		if (nsec >= NS_PER_SEC || nsec <= -NS_PER_SEC) {
			sec += nsec / NS_PER_SEC;
			nsec %= NS_PER_SEC;
		}
		if (nsec < 0) {
			nsec += NS_PER_SEC;
			--sec;
		}
	}

	void normalize() {
		long long sec = static_cast<long long>(ts_.tv_sec);
		long long nsec = static_cast<long long>(ts_.tv_nsec);
		normalize_values(sec, nsec);
		ts_.tv_sec = sec;
		ts_.tv_nsec = static_cast<long>(nsec);
	}

	timestamp operator+(const timestamp& other) const {
		return timestamp(static_cast<long long>(ts_.tv_sec) + static_cast<long long>(other.ts_.tv_sec),
				 static_cast<long long>(ts_.tv_nsec) + static_cast<long long>(other.ts_.tv_nsec));
	}

	timestamp operator-(const timestamp& other) const {
		return timestamp(static_cast<long long>(ts_.tv_sec) - static_cast<long long>(other.ts_.tv_sec),
				 static_cast<long long>(ts_.tv_nsec) - static_cast<long long>(other.ts_.tv_nsec));
	}

	timestamp& operator+=(const timestamp& other) {
		ts_.tv_sec += other.ts_.tv_sec;
		ts_.tv_nsec += other.ts_.tv_nsec;
		normalize();
		return *this;
	}

	timestamp& operator-=(const timestamp& other) {
		ts_.tv_sec -= other.ts_.tv_sec;
		ts_.tv_nsec -= other.ts_.tv_nsec;
		normalize();
		return *this;
	}

	bool operator==(const timestamp& other) const {
		return ts_.tv_sec == other.ts_.tv_sec && ts_.tv_nsec == other.ts_.tv_nsec;
	}

	bool operator!=(const timestamp& other) const { return !(*this == other); }

	bool operator<(const timestamp& other) const {
		if (ts_.tv_sec != other.ts_.tv_sec)
			return ts_.tv_sec < other.ts_.tv_sec;
		return ts_.tv_nsec < other.ts_.tv_nsec;
	}

	bool operator<=(const timestamp& other) const { return !(other < *this); }
	bool operator>(const timestamp& other) const { return other < *this; }
	bool operator>=(const timestamp& other) const { return !(*this < other); }

private:
	enum : long long { NS_PER_SEC = 1000000000LL };
	abi::timespec64 ts_;
};

} // namespace wrappers
} // namespace linuxcpp
