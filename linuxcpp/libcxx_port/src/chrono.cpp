// 内核移植：chrono 的时间源换成内核时钟，不再调用 clock_gettime/timespec_get。
//===----------------------------------------------------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#include <chrono>
#include <ctime>

// 内核时间取纳秒，C 接口由 libc_port.c 提供；这里不 include 内核头，
// 避免内核头宏和 libc++ 头在同一个翻译单元里打架。
extern "C" {
long long lc_ktime_get_real_ns(void);
long long lc_ktime_get_monotonic_ns(void);
}

_LIBCPP_BEGIN_NAMESPACE_STD

namespace chrono {

const bool system_clock::is_steady;

system_clock::time_point system_clock::now() noexcept
{
	return time_point(duration_cast<system_clock::duration>(
		nanoseconds(lc_ktime_get_real_ns())));
}

time_t system_clock::to_time_t(const time_point &t) noexcept
{
	return time_t(duration_cast<seconds>(t.time_since_epoch()).count());
}

system_clock::time_point system_clock::from_time_t(time_t t) noexcept
{
	return time_point(seconds(t));
}

#if _LIBCPP_HAS_MONOTONIC_CLOCK

const bool steady_clock::is_steady;

steady_clock::time_point steady_clock::now() noexcept
{
	return time_point(duration_cast<steady_clock::duration>(
		nanoseconds(lc_ktime_get_monotonic_ns())));
}

#endif  // _LIBCPP_HAS_MONOTONIC_CLOCK

}  // namespace chrono

_LIBCPP_END_NAMESPACE_STD
