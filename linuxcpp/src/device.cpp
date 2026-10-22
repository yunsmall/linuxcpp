// SPDX-License-Identifier: GPL-2.0-only

// char_device / misc_device 现在依赖 CRTP，实现全部在 device.hpp。
// 公共 Makefile 的核心对象列表固定包含 device.o，这里留一个内部符号
// 避免空翻译单元。

namespace {

[[maybe_unused]] constexpr int kDeviceTranslationUnit = 0;

}  // namespace
