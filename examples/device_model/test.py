#!/usr/bin/env python3
"""检查 device_model 模块注册出来的 bus、device、platform 和 sysfs 属性。"""

import sys
from pathlib import Path

ATTR = Path("/sys/bus/lcpp_demo/devices/lcpp_demo0/demo")
PLATFORM_DRIVER = Path("/sys/bus/platform/drivers/lcpp_platform_demo")
PLATFORM_DEVICE = Path("/sys/bus/platform/devices/lcpp_platform_demo.0")


def main():
    missing = [str(path) for path in (ATTR, PLATFORM_DRIVER, PLATFORM_DEVICE)
               if not path.exists()]
    if missing:
        sys.exit("模块没有加载，或注册失败：\n  " + "\n  ".join(missing))

    text = ATTR.read_text(encoding="utf-8").strip()
    if text != "C++ device model works":
        sys.exit(f"属性内容不对: {text!r}")
    print(text)


if __name__ == "__main__":
    main()
