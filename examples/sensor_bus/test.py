#!/usr/bin/env python3
"""检查 sensor_bus 的 bus、驱动、sysfs 属性、device class 和 misc 设备。"""

import errno
import os
import sys
from pathlib import Path

BUS = Path("/sys/bus/lcpp_sensor")
TEMP_VALUE = BUS / "devices/temp0/sensor/value"
TEMP_LABEL = BUS / "devices/temp0/sensor/label"
HUM_VALUE = BUS / "devices/hum0/sensor/value"
TEMP_DRIVER = BUS / "drivers/sensor-temp"
HUM_DRIVER = BUS / "drivers/sensor-hum"
DEVICE_CLASS = Path("/sys/class/lcpp_sensor")
MONITOR = Path("/dev/sensor_monitor")


def write_monitor(text):
    fd = os.open(MONITOR, os.O_WRONLY)
    try:
        os.write(fd, text.encode())
    finally:
        os.close(fd)


def parse_monitor():
    lines = MONITOR.read_text(encoding="utf-8").strip().splitlines()
    return dict(line.split("=", 1) for line in lines)


def main():
    required = (TEMP_VALUE, TEMP_LABEL, HUM_VALUE, TEMP_DRIVER, HUM_DRIVER,
                DEVICE_CLASS, MONITOR)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        sys.exit("模块没有加载，或注册失败：\n  " + "\n  ".join(missing))

    expected = {
        TEMP_VALUE: "21500 milli-C",
        TEMP_LABEL: "temp0 (milli-C)",
        HUM_VALUE: "48000 milli-%RH",
    }
    for path, want in expected.items():
        got = path.read_text(encoding="utf-8").strip()
        if got != want:
            sys.exit(f"{path} 内容不对: {got!r}")

    sensors = parse_monitor()
    if sensors.get("temp0") != "21500 milli-C":
        sys.exit(f"monitor 里的温度不对: {sensors!r}")
    if sensors.get("hum0") != "48000 milli-%RH":
        sys.exit(f"monitor 里的湿度不对: {sensors!r}")

    write_monitor("temp0 12345")
    sensors = parse_monitor()
    if sensors.get("temp0") != "12345 milli-C":
        sys.exit(f"写入后温度没有变化: {sensors!r}")
    print(MONITOR.read_text(encoding="utf-8").strip())

    try:
        write_monitor("bogus 1")
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            sys.exit(f"未知传感器的错误码不对: {exc}")
    else:
        sys.exit("未知传感器没有返回 ENOENT")

    write_monitor("temp0 21500")


if __name__ == "__main__":
    main()
