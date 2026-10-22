// SPDX-License-Identifier: GPL-2.0-only

// 用内核 API 采集统计信息，C++ 侧只消费纯数据结构的快照。

#include "stats_kernel.h"

#include <linux/cpumask.h>
#include <linux/jiffies.h>
#include <linux/kernel.h>
#include <linux/mm.h>
#include <linux/rcupdate.h>
#include <linux/sched.h>
#include <linux/sched/loadavg.h>
#include <linux/sched/signal.h>
#include <linux/string.h>
#include <linux/timekeeping.h>
#include <linux/utsname.h>

static unsigned long long to_bytes(unsigned long value, unsigned int unit)
{
	return (unsigned long long)value * unit;
}

void lc_collect_sys_stats(struct lc_sys_stats *stats)
{
	struct sysinfo info;
	struct timespec64 real;
	struct task_struct *process;
	struct task_struct *thread;
	unsigned int processes = 0;
	unsigned int threads = 0;
	int i;

	memset(stats, 0, sizeof(*stats));
	// 新内核的 si_meminfo 不再填 swap 字段，先清零避免把栈上垃圾带出去
	memset(&info, 0, sizeof(info));

	si_meminfo(&info);
	stats->totalram_bytes = to_bytes(info.totalram, info.mem_unit);
	stats->freeram_bytes = to_bytes(info.freeram, info.mem_unit);
	stats->availableram_bytes =
		to_bytes((unsigned long)si_mem_available(), info.mem_unit);
	stats->sharedram_bytes = to_bytes(info.sharedram, info.mem_unit);
	stats->bufferram_bytes = to_bytes(info.bufferram, info.mem_unit);
	stats->totalhigh_bytes = to_bytes(info.totalhigh, info.mem_unit);
	stats->freehigh_bytes = to_bytes(info.freehigh, info.mem_unit);

	ktime_get_real_ts64(&real);
	stats->realtime_sec = real.tv_sec;
	stats->realtime_nsec = real.tv_nsec;
	stats->uptime_ns = ktime_get_ns();
	// jiffies_64 的起点是 INITIAL_JIFFIES（负数），减掉才是开机后的节拍数
	stats->jiffies = get_jiffies_64() - INITIAL_JIFFIES;

	for (i = 0; i < 3; ++i)
		stats->loadavg_hundredths[i] =
			(unsigned int)((avenrun[i] * 100 + (1 << (FSHIFT - 1))) >> FSHIFT);

	stats->page_size = PAGE_SIZE;
	stats->hz = HZ;
	stats->online_cpus = num_online_cpus();
	stats->possible_cpus = num_possible_cpus();
	stats->nr_cpu_ids = nr_cpu_ids;

	// 进程链表必须在 RCU 读侧遍历；线程数按每个进程的 thread group 累加
	rcu_read_lock();
	for_each_process(process) {
		++processes;
		for_each_thread(process, thread)
			++threads;
	}
	rcu_read_unlock();

	stats->processes = processes;
	stats->threads = threads;

	snprintf(stats->release, sizeof(stats->release), "%s",
		 init_uts_ns.name.release);
	snprintf(stats->hostname, sizeof(stats->hostname), "%s",
		 init_uts_ns.name.nodename);
}
