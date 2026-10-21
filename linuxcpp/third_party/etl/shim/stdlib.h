/* 由 gen_libc_shim.py 生成，不要手改 */
#pragma once
static inline int abs(int x) { return x < 0 ? -x : x; }
static inline long labs(long x) { return x < 0 ? -x : x; }
