"""生成模块目录里的入口 Makefile。

只在模块目录还没有 Makefile 时初始化一次。之后 Makefile 归用户维护，
新增源文件直接改 <模块名>-y；构建 driver 不会扫描目录，也不会覆盖它。
"""

import os
import sys

from paths import LIB_DIR


def write_makefile(module_dir, config, kdir, entry_obj, objects):
    path = module_dir / "Makefile"
    if path.exists():
        return

    object_text = " ".join(objects)
    rel_linuxcpp = os.path.relpath(LIB_DIR, module_dir).replace(os.sep, "/")
    content = f"""\
# 由 build.py 初始化生成；之后新增源文件请直接改 {config["name"]}-y
KDIR ?= /lib/modules/$(shell uname -r)/build
PYTHON ?= python3
LINUXCPP ?= {rel_linuxcpp}

ifeq ($(LINUXCPP_BUILD),)
# 直接 make：交给 driver；driver include 本文件时这段不会生效
all:
\t@$(MAKE) -C $(LINUXCPP) M=$(CURDIR) KDIR="$(KDIR)" PYTHON="$(PYTHON)"

clean:
\t@$(MAKE) -C $(LINUXCPP) M=$(CURDIR) KDIR="$(KDIR)" PYTHON="$(PYTHON)" clean

else
# 和 kbuild 一样声明最终模块和对象列表；对象名对应 driver.cpp / driver.c
obj-m := {config["name"]}.o
{config["name"]}-y := {object_text}
LCPP_ENTRY_OBJ := {entry_obj}

# C 库子集独立于 libc++；不用 libc++ 也可以直接用 <string.h>/<stdlib.h> 等
include $(LINUXCPP)/libc.mk

# 需要共享 libc++ 时取消注释；运行库要先构建并 insmod
# include $(LINUXCPP)/libcxx.mk
# KBUILD_EXTRA_SYMBOLS := $(LINUXCPP)/runtime/Module.symvers
endif
"""
    path.write_text(content, encoding="utf-8")
