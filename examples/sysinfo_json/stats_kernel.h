// SPDX-License-Identifier: GPL-2.0-only

// 内核统计快照。这个头只放普通 C 类型，C 和 C++ 都能包含；
// 内核头的细节留在 stats_kernel.c 里，不污染 C++ 翻译单元。

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

struct lc_sys_stats {
	unsigned long long jiffies;
	unsigned long long uptime_ns;
	long long realtime_sec;
	unsigned long realtime_nsec;

	unsigned long long totalram_bytes;
	unsigned long long freeram_bytes;
	unsigned long long availableram_bytes;
	unsigned long long sharedram_bytes;
	unsigned long long bufferram_bytes;
	unsigned long long totalhigh_bytes;
	unsigned long long freehigh_bytes;

	unsigned long long page_size;
	unsigned long long hz;
	unsigned int online_cpus;
	unsigned int possible_cpus;
	unsigned int nr_cpu_ids;
	unsigned int processes;
	unsigned int threads;

	// 负载的百分之一，例如 123 表示 1.23
	unsigned int loadavg_hundredths[3];

	char release[64];
	char hostname[64];
};

void lc_collect_sys_stats(struct lc_sys_stats *stats);

#ifdef __cplusplus
}
#endif
