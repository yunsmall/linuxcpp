"""生成模块目录里的入口 Makefile。

被 linuxcpp/Makefile include 时（LINUXCPP_BUILD 非空）只保留 kbuild 风格声明；
直接 make 时把工作转交给 driver，这样模块自己的目标不会和公共规则抢所有权。
"""

import sys

from paths import LIB_DIR

MAKEFILE_MARKER = "# 由 build.py 自动生成"


def write_makefile(module_dir, config, kdir, entry_obj, objects):
    object_text = " ".join(objects)
    content = f"""\
{MAKEFILE_MARKER}
KDIR ?= {kdir}
PYTHON ?= {sys.executable}
LINUXCPP ?= {LIB_DIR}

ifeq ($(LINUXCPP_BUILD),)
# 直接 make：交给 driver；driver include 本文件时这段不会生效
all:
\t$(MAKE) -C $(LINUXCPP) M=$(CURDIR) KDIR="$(KDIR)" PYTHON="$(PYTHON)"

clean:
\t$(MAKE) -C $(LINUXCPP) M=$(CURDIR) KDIR="$(KDIR)" PYTHON="$(PYTHON)" clean

else
MODULE_NAME := {config["name"]}
obj-m := $(MODULE_NAME).o
$(MODULE_NAME)-y := {object_text}
LCPP_ENTRY_OBJ := {entry_obj}
endif
"""
    path = module_dir / "Makefile"
    if path.exists():
        old = path.read_text(encoding="utf-8")
        if not old.startswith(MAKEFILE_MARKER):
            # 手写 Makefile 由用户自己维护，这里只准备生成物，不能覆盖
            print(f"保留手写 Makefile: {path}")
            return
        if old == content:
            return
    path.write_text(content, encoding="utf-8")
