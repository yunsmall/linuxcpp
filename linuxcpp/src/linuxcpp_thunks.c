// SPDX-License-Identifier: GPL-3.0-or-later

// 核心库固定需要的 C thunk：宏和初始化函数没法从内核头自动提取。

#include <linux/atomic.h>
#include <linux/mutex.h>
#include <linux/printk.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/stdarg.h>

void *lc_kmalloc(size_t size);
void lc_kfree(void *ptr);
void lc_printk(const char *fmt, ...);
void lc_mutex_init(struct mutex *mutex);
void lc_mutex_destroy(struct mutex *mutex);
void lc_mutex_lock(struct mutex *mutex);
void lc_mutex_unlock(struct mutex *mutex);
void lc_spin_lock_init(spinlock_t *lock);
int lc_atomic_read(const atomic_t *value);
void lc_atomic_set(atomic_t *value, int v);
void lc_atomic_add(int v, atomic_t *value);
void lc_atomic_sub(int v, atomic_t *value);
void lc_atomic_inc(atomic_t *value);
void lc_atomic_dec(atomic_t *value);

void *lc_kmalloc(size_t size)
{
	return kmalloc(size, GFP_KERNEL);
}

void lc_kfree(void *ptr)
{
	kfree(ptr);
}

// C++ 的变参函数不能直接转发给 printk，用 vprintk 接住 va_list
void lc_printk(const char *fmt, ...)
{
	va_list args;

	va_start(args, fmt);
	vprintk(fmt, args);
	va_end(args);
}

void lc_mutex_init(struct mutex *mutex)
{
	mutex_init(mutex);
}

void lc_mutex_destroy(struct mutex *mutex)
{
	// 调试配置下 mutex_destroy 会清理持有者记录，跳过它会让 lockdep 报残留状态
	mutex_destroy(mutex);
}

void lc_mutex_lock(struct mutex *mutex)
{
	mutex_lock(mutex);
}

void lc_mutex_unlock(struct mutex *mutex)
{
	mutex_unlock(mutex);
}

// spin_lock_init 是宏，自动 thunk 生成器看不到函数定义
void lc_spin_lock_init(spinlock_t *lock)
{
	spin_lock_init(lock);
}

// atomic 系列在部分架构上是宏，自动生成的参数类型会写成 struct atomic_t
int lc_atomic_read(const atomic_t *value)
{
	return atomic_read(value);
}

void lc_atomic_set(atomic_t *value, int v)
{
	atomic_set(value, v);
}

void lc_atomic_add(int v, atomic_t *value)
{
	atomic_add(v, value);
}

void lc_atomic_sub(int v, atomic_t *value)
{
	atomic_sub(v, value);
}

void lc_atomic_inc(atomic_t *value)
{
	atomic_inc(value);
}

void lc_atomic_dec(atomic_t *value)
{
	atomic_dec(value);
}
