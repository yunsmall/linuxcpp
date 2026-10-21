/* 由 gen_libc_shim.py 生成，不要手改 */
#pragma once
#define assert(cond) do { if (!(cond)) __builtin_trap(); } while (0)
