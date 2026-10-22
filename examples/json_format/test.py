#!/usr/bin/env python3
"""调用 /dev/json_format，把传入的 JSON 文件原地格式化。"""

import fcntl
import json
import os
import sys
import tempfile

JSON_FORMAT = 0x4A01
DEVICE = "/dev/json_format"


def format_file(path):
    file_fd = os.open(path, os.O_RDWR)
    device_fd = os.open(DEVICE, os.O_RDWR)
    try:
        fcntl.ioctl(device_fd, JSON_FORMAT, file_fd)
    finally:
        os.close(device_fd)
        os.close(file_fd)


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
        format_file(path)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    else:
        with tempfile.NamedTemporaryFile("w+", suffix=".json",
                                         delete=False) as handle:
            path = handle.name
            handle.write('{"kernel":{"name":"linux","cpus":[1,2,3]},'
                         '"ok":true,"value":123.5}')
        format_file(path)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        os.unlink(path)

    json.loads(text)
    print(text)

    # 解析失败必须让 ioctl 返回 EINVAL
    with tempfile.NamedTemporaryFile("w+", suffix=".json",
                                     delete=False) as handle:
        path = handle.name
        handle.write('{"broken": [1,}')
    try:
        try:
            format_file(path)
        except OSError as error:
            print(f"invalid json -> errno {error.errno}")
        else:
            raise SystemExit("invalid json was accepted")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    main()
