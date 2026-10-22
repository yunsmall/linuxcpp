// SPDX-License-Identifier: GPL-2.0-only

// 核心库固定需要的 C thunk：宏和初始化函数没法从内核头自动提取。

#include <linux/atomic.h>
#include <linux/bug.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/printk.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/stdarg.h>

void *lc_kmalloc(size_t size);
void lc_kfree(void *ptr);
void lc_might_sleep(void);
void *lc_this_module(void);
void lc_printk(const char *fmt, ...);
void lc_bug(void) __attribute__((noreturn));
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

// C++ 的 operator new 只会用 GFP_KERNEL；在原子上下文里调用时让内核
// 立刻打印调用栈，而不是等到 schedule 时才发现问题
void lc_might_sleep(void)
{
	might_sleep();
}

// C++ 侧拿不到 THIS_MODULE 宏；驱动注册要把当前模块的 owner 传给内核
void *lc_this_module(void)
{
	return THIS_MODULE;
}

// C++ 的变参函数不能直接转发给 printk，用 vprintk 接住 va_list
void lc_printk(const char *fmt, ...)
{
	va_list args;

	va_start(args, fmt);
	vprintk(fmt, args);
	va_end(args);
}

// libc++ 在 -fno-exceptions 下把断言失败交给这个入口；内核里没有异常，
// 只能打印原因后 BUG，留下调用栈方便定位
__attribute__((noreturn)) void lc_bug(void)
{
	BUG();
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
